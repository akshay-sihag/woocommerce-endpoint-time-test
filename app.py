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
) -> Tuple[Any, Dict[str, Any]]:
    start = time.perf_counter_ns()
    try:
        r = requests.get(url, headers=headers, timeout=timeout_s, verify=verify_tls, auth=auth)
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
        meta = {
            "ok": bool(r.ok),
            "status": r.status_code,
            "elapsed_ms": elapsed_ms,
            "bytes": len(r.content) if r.content is not None else 0,
            "url": url,
            "error": None,
        }
        if not r.ok:
            meta["error"] = r.text[:4000]
            return None, meta
        try:
            return r.json(), meta
        except Exception as e:
            meta["ok"] = False
            meta["error"] = f"JSON decode failed: {e}. First 800 chars: {r.text[:800]}"
            return None, meta
    except Exception as e:
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
        return None, {
            "ok": False,
            "status": None,
            "elapsed_ms": elapsed_ms,
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
    q = f"email={quote_plus(email.strip())}"
    extra_q = extra.strip()
    if extra_q:
        q = f"{q}&{extra_q}"
    return f"{base.rstrip('/')}{path}?{q}"


def wc_url(base: str, path: str, q: str) -> str:
    q2 = q.strip()
    if q2:
        return f"{base.rstrip('/')}{path}?{q2}"
    return f"{base.rstrip('/')}{path}"


def subscription_ids_from_subscriptions_payload(subs_payload: Any) -> List[int]:
    if not isinstance(subs_payload, list):
        return []
    ids: List[int] = []
    for sub in subs_payload:
        if isinstance(sub, dict):
            sid = sub.get("id")
            if isinstance(sid, int):
                ids.append(sid)
            elif isinstance(sid, str) and sid.isdigit():
                ids.append(int(sid))
    seen = set()
    out: List[int] = []
    for sid in ids:
        if sid not in seen:
            out.append(sid)
            seen.add(sid)
    return out


def safe_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def filter_orders_required(payload: Any) -> Any:
    if not isinstance(payload, list):
        return payload
    out: List[Dict[str, Any]] = []
    for o in payload:
        o = safe_dict(o)
        line_items_in = safe_list(o.get("line_items"))
        line_items_out: List[Dict[str, Any]] = []
        for li in line_items_in:
            li = safe_dict(li)
            img = safe_dict(li.get("image"))
            line_items_out.append(
                {
                    "name": li.get("name"),
                    "quantity": li.get("quantity"),
                    "total": li.get("total"),
                    "image": {"src": img.get("src")},
                }
            )
        out.append(
            {
                "id": o.get("id"),
                "number": o.get("number"),
                "status": o.get("status"),
                "date_created": o.get("date_created"),
                "total": o.get("total"),
                "currency": o.get("currency"),
                "line_items": line_items_out,
            }
        )
    return out


def filter_subscriptions_required(payload: Any) -> Any:
    if not isinstance(payload, list):
        return payload
    out: List[Dict[str, Any]] = []
    for s in payload:
        s = safe_dict(s)
        billing = safe_dict(s.get("billing"))
        line_items_in = safe_list(s.get("line_items"))
        line_items_out: List[Dict[str, Any]] = []
        for li in line_items_in:
            li = safe_dict(li)
            img = safe_dict(li.get("image"))
            line_items_out.append(
                {
                    "name": li.get("name"),
                    "quantity": li.get("quantity"),
                    "total": li.get("total"),
                    "image": {"src": img.get("src")},
                }
            )
        out.append(
            {
                "id": s.get("id"),
                "status": s.get("status"),
                "date_created": s.get("date_created"),
                "next_payment_date": s.get("next_payment_date"),
                "total": s.get("total"),
                "currency": s.get("currency"),
                "billing_email": billing.get("email"),
                "line_items": line_items_out,
            }
        )
    return out


def measure_filter(fn, data: Any) -> Tuple[Any, float]:
    t0 = time.perf_counter_ns()
    out = fn(data)
    t1 = time.perf_counter_ns()
    return out, (t1 - t0) / 1_000_000.0


def render_block(title: str, data: Any, meta: Dict[str, Any], filter_ms: Optional[float], key: str):
    st.subheader(title)
    st.write(f"Status: {meta.get('status')}  OK: {meta.get('ok')}")
    st.write(f"API time: {format_duration(float(meta.get('elapsed_ms', 0.0)))}")
    if filter_ms is not None:
        st.write(f"Filter time: {format_duration(float(filter_ms))}")
        st.write(f"API plus filter: {format_duration(float(meta.get('elapsed_ms', 0.0)) + float(filter_ms))}")
    st.write(f"Bytes: {meta.get('bytes')}")
    st.code(meta.get("url", ""), language="text")
    if meta.get("error"):
        st.text_area("Error", value=str(meta["error"]), height=140, key=f"{key}_err")
    st.text_area("JSON", value=pretty_json(data) if data is not None else "null", height=360, key=key)


def run_proxy(email: str, proxy_base: str, proxy_key: str, timeout: float, verify: bool, extra: str):
    headers = build_proxy_headers(proxy_key)

    orders_full, m_orders = timed_get_json(
        proxy_url(proxy_base, "/api/woocommerce/orders", email, extra),
        headers,
        timeout,
        verify,
        None,
    )
    subs_full, m_subs = timed_get_json(
        proxy_url(proxy_base, "/api/woocommerce/subscriptions", email, extra),
        headers,
        timeout,
        verify,
        None,
    )

    return orders_full, m_orders, subs_full, m_subs


def run_proxy_subscription_orders(email: str, proxy_base: str, proxy_key: str, timeout: float, verify: bool, extra: str, sub_ids: List[int]):
    headers = build_proxy_headers(proxy_key)
    results: List[Tuple[int, Any, Dict[str, Any]]] = []
    for sid in sub_ids:
        data, meta = timed_get_json(
            proxy_url(proxy_base, f"/api/woocommerce/subscriptions/{sid}/orders", email, extra),
            headers,
            timeout,
            verify,
            None,
        )
        results.append((sid, data, meta))
    return results


def run_wc(email: str, wc_base: str, ck: str, cs: str, timeout: float, verify: bool, extra: str):
    auth = (ck, cs)

    customers, m_cust = timed_get_json(
        wc_url(wc_base, "/wp-json/wc/v3/customers", f"role=all&email={quote_plus(email.strip())}&per_page=10"),
        {"Accept": "application/json"},
        timeout,
        verify,
        auth,
    )

    cid = None
    if isinstance(customers, list) and customers and isinstance(customers[0], dict):
        if isinstance(customers[0].get("id"), int):
            cid = customers[0]["id"]

    orders_full = subs_full = None
    m_orders = {"ok": False, "status": None, "elapsed_ms": 0.0, "bytes": 0, "url": "", "error": "No customer id resolved"}
    m_subs = {"ok": False, "status": None, "elapsed_ms": 0.0, "bytes": 0, "url": "", "error": "No customer id resolved"}

    if cid is not None:
        q_orders = f"customer={cid}&{extra.strip()}" if extra.strip() else f"customer={cid}"
        orders_full, m_orders = timed_get_json(
            wc_url(wc_base, "/wp-json/wc/v3/orders", q_orders),
            {"Accept": "application/json"},
            timeout,
            verify,
            auth,
        )

        q_subs = f"customer={cid}&{extra.strip()}" if extra.strip() else f"customer={cid}"
        subs_full, m_subs = timed_get_json(
            wc_url(wc_base, "/wp-json/wc/v1/subscriptions", q_subs),
            {"Accept": "application/json"},
            timeout,
            verify,
            auth,
        )

    return customers, m_cust, orders_full, m_orders, subs_full, m_subs


def run_wc_subscription_orders(wc_base: str, ck: str, cs: str, timeout: float, verify: bool, extra: str, sub_ids: List[int]):
    auth = (ck, cs)
    results: List[Tuple[int, Any, Dict[str, Any]]] = []
    for sid in sub_ids:
        data, meta = timed_get_json(
            wc_url(wc_base, f"/wp-json/wc/v1/subscriptions/{sid}/orders", extra.strip()),
            {"Accept": "application/json"},
            timeout,
            verify,
            auth,
        )
        results.append((sid, data, meta))
    return results


def main():
    st.set_page_config(page_title="Woo API Speed Tester", layout="wide")
    st.title("Woo API Speed Tester")

    proxy_base = get_secret("PROXY_BASE_URL", "https://appanel.alternatehealthclub.com").strip()
    proxy_key = get_secret("PROXY_API_KEY", "").strip()

    wc_base = get_secret("WC_BASE_URL", "https://alternatehealthclub.com").strip()
    wc_ck = get_secret("WC_CONSUMER_KEY", "").strip()
    wc_cs = get_secret("WC_CONSUMER_SECRET", "").strip()

    timeout = float(get_secret("TIMEOUT_SECONDS", "60").strip() or "60")
    verify = get_secret("VERIFY_TLS", "true").lower().strip() not in ("0", "false", "no")

    st.sidebar.header("Controls")
    method = st.sidebar.selectbox("Fetch method", ["Proxy App Panel", "Direct WooCommerce"], index=0)
    email = st.sidebar.text_input("Customer email", value="")
    extra = st.sidebar.text_input("Extra query params", value="per_page=100")
    max_subs_to_expand = st.sidebar.number_input("Max subscriptions to expand into orders", min_value=0, max_value=50, value=10, step=1)

    if st.button("Run Full and Required Fetch"):
        if not email.strip():
            st.error("Email is required")
            return

        if method == "Proxy App Panel":
            if not proxy_key:
                st.error("PROXY_API_KEY is missing")
                return

            orders_full, m_orders = run_proxy(email, proxy_base, proxy_key, timeout, verify, extra)
            subs_full, m_subs = timed_get_json(
                proxy_url(proxy_base, "/api/woocommerce/subscriptions", email, extra),
                build_proxy_headers(proxy_key),
                timeout,
                verify,
                None,
            )

            sub_ids = subscription_ids_from_subscriptions_payload(subs_full)
            if max_subs_to_expand > 0:
                sub_ids = sub_ids[: int(max_subs_to_expand)]

            orders_req, orders_filter_ms = measure_filter(filter_orders_required, orders_full)
            subs_req, subs_filter_ms = measure_filter(filter_subscriptions_required, subs_full)

            left, right = st.columns(2)

            with left:
                render_block("Orders full", orders_full, m_orders, None, "proxy_orders_full")
                render_block("Subscriptions full", subs_full, m_subs, None, "proxy_subs_full")

            with right:
                render_block("Orders required", orders_req, m_orders, orders_filter_ms, "proxy_orders_req")
                render_block("Subscriptions required", subs_req, m_subs, subs_filter_ms, "proxy_subs_req")

            st.header("Subscription orders")
            st.write(f"Subscription ids used: {sub_ids}")

            sub_orders_full = run_proxy_subscription_orders(email, proxy_base, proxy_key, timeout, verify, extra, sub_ids)
            for sid, data_full, meta_full in sub_orders_full:
                data_req, fms = measure_filter(filter_orders_required, data_full)
                a, b = st.columns(2)
                with a:
                    render_block(f"Subscription {sid} orders full", data_full, meta_full, None, f"proxy_sub_{sid}_full")
                with b:
                    render_block(f"Subscription {sid} orders required", data_req, meta_full, fms, f"proxy_sub_{sid}_req")

        else:
            if not wc_ck or not wc_cs:
                st.error("WC_CONSUMER_KEY and WC_CONSUMER_SECRET are required")
                return

            customers, m_cust, orders_full, m_orders, subs_full, m_subs = run_wc(email, wc_base, wc_ck, wc_cs, timeout, verify, extra)

            sub_ids = subscription_ids_from_subscriptions_payload(subs_full)
            if max_subs_to_expand > 0:
                sub_ids = sub_ids[: int(max_subs_to_expand)]

            orders_req, orders_filter_ms = measure_filter(filter_orders_required, orders_full)
            subs_req, subs_filter_ms = measure_filter(filter_subscriptions_required, subs_full)

            left, right = st.columns(2)

            with left:
                render_block("Customer lookup full", customers, m_cust, None, "wc_customers_full")
                render_block("Orders full", orders_full, m_orders, None, "wc_orders_full")
                render_block("Subscriptions full", subs_full, m_subs, None, "wc_subs_full")

            with right:
                render_block("Orders required", orders_req, m_orders, orders_filter_ms, "wc_orders_req")
                render_block("Subscriptions required", subs_req, m_subs, subs_filter_ms, "wc_subs_req")

            st.header("Subscription orders")
            st.write(f"Subscription ids used: {sub_ids}")

            sub_orders_full = run_wc_subscription_orders(wc_base, wc_ck, wc_cs, timeout, verify, extra, sub_ids)
            for sid, data_full, meta_full in sub_orders_full:
                data_req, fms = measure_filter(filter_orders_required, data_full)
                a, b = st.columns(2)
                with a:
                    render_block(f"Subscription {sid} orders full", data_full, meta_full, None, f"wc_sub_{sid}_full")
                with b:
                    render_block(f"Subscription {sid} orders required", data_req, meta_full, fms, f"wc_sub_{sid}_req")


if __name__ == "__main__":
    main()
