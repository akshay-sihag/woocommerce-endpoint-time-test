# app.py
import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests
import streamlit as st


def pretty_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_duration(ms: float) -> str:
    return f"{ms:.3f} ms | {ms/1000.0:.3f} s"


def timed_get_json(
    url: str,
    headers: Dict[str, str],
    timeout_s: float,
    verify_tls: bool,
    auth: Optional[Tuple[str, str]] = None,
):
    start = time.perf_counter_ns()
    try:
        r = requests.get(url, headers=headers, timeout=timeout_s, verify=verify_tls, auth=auth)
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
        if not r.ok:
            return None, {
                "ok": False,
                "status": r.status_code,
                "elapsed_ms": elapsed,
                "bytes": len(r.content),
                "url": url,
                "error": r.text[:3000],
            }
        return r.json(), {
            "ok": True,
            "status": r.status_code,
            "elapsed_ms": elapsed,
            "bytes": len(r.content),
            "url": url,
            "error": None,
        }
    except Exception as e:
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
        return None, {
            "ok": False,
            "status": None,
            "elapsed_ms": elapsed,
            "bytes": 0,
            "url": url,
            "error": str(e),
        }


def get_secret(key: str, default: str = "") -> str:
    return str(st.secrets.get(key, os.getenv(key, default))).strip()


def build_proxy_headers(api_key: str) -> Dict[str, str]:
    return {
        "X-API-Key": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def proxy_url(base: str, path: str, email: str, extra: str) -> str:
    q = f"email={quote_plus(email)}"
    if extra.strip():
        q += f"&{extra.strip()}"
    return f"{base}{path}?{q}"


def wc_url(base: str, path: str, q: str) -> str:
    return f"{base}{path}?{q}" if q else f"{base}{path}"


def collect_ids(payload: Any) -> List[int]:
    ids = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("id", "subscription_id") and str(v).isdigit():
                    ids.append(int(v))
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(payload)
    return list(dict.fromkeys(ids))


def render(title: str, data: Any, meta: Dict[str, Any], key: str):
    st.subheader(title)
    st.write(f"Status: {meta['status']} | OK: {meta['ok']}")
    st.write(f"Time: {format_duration(meta['elapsed_ms'])}")
    st.write(f"Bytes: {meta['bytes']}")
    st.code(meta["url"], language="text")

    if meta["error"]:
        st.text_area("Error", meta["error"], height=120, key=f"{key}_err")

    st.text_area("JSON", pretty_json(data) if data else "null", height=360, key=key)


def run_proxy(email, base, key, timeout, verify, extra):
    headers = build_proxy_headers(key)

    orders, m1 = timed_get_json(
        proxy_url(base, "/api/woocommerce/orders", email, extra),
        headers,
        timeout,
        verify,
    )

    subs, m2 = timed_get_json(
        proxy_url(base, "/api/woocommerce/subscriptions", email, extra),
        headers,
        timeout,
        verify,
    )

    ids = collect_ids(subs)

    sub_orders = []
    for sid in ids:
        data, m = timed_get_json(
            proxy_url(base, f"/api/woocommerce/subscriptions/{sid}/orders", email, extra),
            headers,
            timeout,
            verify,
        )
        sub_orders.append((sid, data, m))

    return orders, m1, subs, m2, sub_orders


def run_wc(email, base, ck, cs, timeout, verify, extra):
    auth = (ck, cs)

    cust, cm = timed_get_json(
        wc_url(
            base,
            "/wp-json/wc/v3/customers",
            f"role=all&email={quote_plus(email)}",
        ),
        {"Accept": "application/json"},
        timeout,
        verify,
        auth,
    )

    cid = cust[0]["id"] if isinstance(cust, list) and cust else None

    orders = subs = None
    m1 = m2 = {"ok": False, "status": None, "elapsed_ms": 0, "bytes": 0, "url": "", "error": "No customer id"}

    if cid:
        orders, m1 = timed_get_json(
            wc_url(base, "/wp-json/wc/v3/orders", f"customer={cid}&{extra}"),
            {"Accept": "application/json"},
            timeout,
            verify,
            auth,
        )

        subs, m2 = timed_get_json(
            wc_url(base, "/wp-json/wc/v1/subscriptions", f"customer={cid}&{extra}"),
            {"Accept": "application/json"},
            timeout,
            verify,
            auth,
        )

    ids = collect_ids(subs)

    sub_orders = []
    for sid in ids:
        data, m = timed_get_json(
            wc_url(base, f"/wp-json/wc/v1/subscriptions/{sid}/orders", extra),
            {"Accept": "application/json"},
            timeout,
            verify,
            auth,
        )
        sub_orders.append((sid, data, m))

    return cust, cm, orders, m1, subs, m2, sub_orders


def main():
    st.set_page_config(layout="wide")
    st.title("Woo API Speed Comparison")

    proxy_base = get_secret("PROXY_BASE_URL")
    proxy_key = get_secret("PROXY_API_KEY")
    wc_base = get_secret("WC_BASE_URL")
    wc_ck = get_secret("WC_CONSUMER_KEY")
    wc_cs = get_secret("WC_CONSUMER_SECRET")

    timeout = float(get_secret("TIMEOUT_SECONDS", "60"))
    verify = get_secret("VERIFY_TLS", "true").lower() not in ("0", "false")

    method = st.selectbox("Fetch method", ["Proxy App Panel", "Direct WooCommerce"])
    email = st.text_input("Customer email")
    extra = st.text_input("Extra query params", value="per_page=100")

    if st.button("Run API Calls"):
        if not email.strip():
            st.error("Email is required")
            return

        col1, col2 = st.columns(2)

        if method == "Proxy App Panel":
            o, m1, s, m2, so = run_proxy(email, proxy_base, proxy_key, timeout, verify, extra)
            with col1:
                render("Orders (Full)", o, m1, "p_orders")
            with col2:
                render("Subscriptions (Full)", s, m2, "p_subs")
            for sid, d, m in so:
                render(f"Subscription {sid} Orders", d, m, f"p_sub_{sid}")

        else:
            c, cm, o, m1, s, m2, so = run_wc(email, wc_base, wc_ck, wc_cs, timeout, verify, extra)
            with col1:
                render("Customer Lookup", c, cm, "w_cust")
                render("Orders (Full)", o, m1, "w_orders")
            with col2:
                render("Subscriptions (Full)", s, m2, "w_subs")
            for sid, d, m in so:
                render(f"Subscription {sid} Orders", d, m, f"w_sub_{sid}")


if __name__ == "__main__":
    main()
