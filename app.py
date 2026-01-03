import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests
import streamlit as st


def pretty_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_duration(elapsed_ms: float) -> str:
    return f"{elapsed_ms:.3f} ms  |  {elapsed_ms/1000.0:.3f} s"


def normalize_to_list(payload: Any) -> List[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    return [payload]


def safe_get(d: Any, path: List[str], default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def timed_get(
    url: str,
    headers: Dict[str, str],
    timeout_s: float,
    verify_tls: bool,
    auth: Optional[Tuple[str, str]] = None,
) -> Tuple[Optional[requests.Response], Dict[str, Any]]:
    t0 = time.perf_counter_ns()
    try:
        resp = requests.get(url, headers=headers, timeout=timeout_s, verify=verify_tls, auth=auth)
        t1 = time.perf_counter_ns()
        elapsed_ms = (t1 - t0) / 1_000_000.0
        metrics = {
            "ok": resp.ok,
            "status_code": resp.status_code,
            "elapsed_ms": elapsed_ms,
            "elapsed_s": elapsed_ms / 1000.0,
            "bytes": len(resp.content) if resp.content is not None else 0,
            "url": url,
            "error": None,
        }
        if not resp.ok:
            metrics["error"] = resp.text[:2000]
        return resp, metrics
    except requests.RequestException as e:
        t1 = time.perf_counter_ns()
        elapsed_ms = (t1 - t0) / 1_000_000.0
        return None, {
            "ok": False,
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "elapsed_s": elapsed_ms / 1000.0,
            "bytes": 0,
            "url": url,
            "error": str(e),
        }


def timed_get_json(
    url: str,
    headers: Dict[str, str],
    timeout_s: float,
    verify_tls: bool,
    auth: Optional[Tuple[str, str]] = None,
) -> Tuple[Optional[Any], Dict[str, Any]]:
    resp, metrics = timed_get(url, headers, timeout_s, verify_tls, auth=auth)
    if resp is None or not metrics.get("ok"):
        return None, metrics
    try:
        return resp.json(), metrics
    except Exception as e:
        metrics["ok"] = False
        metrics["error"] = f"JSON decode failed: {e}. First 500 chars: {resp.text[:500]}"
        return None, metrics


def collect_subscription_ids(payload: Any) -> List[int]:
    found: List[int] = []

    def visit(node: Any):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("id", "subscription_id"):
                    if isinstance(v, int):
                        found.append(v)
                    elif isinstance(v, str) and v.isdigit():
                        found.append(int(v))
                visit(v)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)

    unique: List[int] = []
    seen = set()
    for x in found:
        if x not in seen:
            unique.append(x)
            seen.add(x)
    return unique


def filter_subscription_item(sub: Dict[str, Any]) -> Dict[str, Any]:
    billing = safe_get(sub, ["billing"], {}) or {}
    shipping = safe_get(sub, ["shipping"], {}) or {}

    line_items_in = safe_get(sub, ["line_items"], []) or []
    line_items_out = []
    for li in normalize_to_list(line_items_in):
        if not isinstance(li, dict):
            continue
        line_items_out.append(
            {
                "name": li.get("name"),
                "quantity": li.get("quantity"),
                "total": li.get("total"),
                "image": {"src": safe_get(li, ["image", "src"])},
            }
        )

    return {
        "id": sub.get("id") if sub.get("id") is not None else sub.get("subscription_id"),
        "number": sub.get("number"),
        "status": sub.get("status"),
        "date_created": sub.get("date_created"),
        "next_payment_date": sub.get("next_payment_date"),
        "end_date": sub.get("end_date"),
        "currency": sub.get("currency"),
        "total": sub.get("total"),
        "billing_period": sub.get("billing_period"),
        "billing_interval": sub.get("billing_interval"),
        "billing": {
            "first_name": billing.get("first_name"),
            "last_name": billing.get("last_name"),
            "address_1": billing.get("address_1"),
            "address_2": billing.get("address_2"),
            "city": billing.get("city"),
            "state": billing.get("state"),
            "postcode": billing.get("postcode"),
            "country": billing.get("country"),
            "email": billing.get("email"),
            "phone": billing.get("phone"),
        },
        "shipping": {
            "first_name": shipping.get("first_name"),
            "last_name": shipping.get("last_name"),
            "address_1": shipping.get("address_1"),
            "address_2": shipping.get("address_2"),
            "city": shipping.get("city"),
            "state": shipping.get("state"),
            "postcode": shipping.get("postcode"),
            "country": shipping.get("country"),
        },
        "line_items": line_items_out,
        "payment_method_title": sub.get("payment_method_title"),
        "payment_method": sub.get("payment_method"),
        "shipping_total": sub.get("shipping_total"),
        "shipping_method": sub.get("shipping_method"),
    }


def filter_order_item(order: Dict[str, Any]) -> Dict[str, Any]:
    line_items_in = safe_get(order, ["line_items"], []) or []
    line_items_out = []
    for li in normalize_to_list(line_items_in):
        if not isinstance(li, dict):
            continue
        line_items_out.append(
            {
                "name": li.get("name"),
                "quantity": li.get("quantity"),
                "total": li.get("total"),
                "image": {"src": safe_get(li, ["image", "src"])},
            }
        )

    meta_in = safe_get(order, ["meta_data"], []) or []
    meta_out = []
    for m in normalize_to_list(meta_in):
        if not isinstance(m, dict):
            continue
        meta_out.append({"key": m.get("key"), "value": m.get("value")})

    return {
        "id": order.get("id"),
        "number": order.get("number"),
        "date_created": order.get("date_created"),
        "status": order.get("status"),
        "total": order.get("total"),
        "currency": order.get("currency"),
        "line_items": line_items_out,
        "meta_data": meta_out,
    }


def filter_orders_payload(payload: Any) -> Any:
    if isinstance(payload, list):
        return [filter_order_item(x) for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        return filter_order_item(payload)
    return payload


def filter_subscriptions_payload(payload: Any) -> Any:
    if isinstance(payload, list):
        return [filter_subscription_item(x) for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        return filter_subscription_item(payload)
    return payload


def render_json_textarea(key: str, data: Any, height: int = 320):
    if data is None:
        st.text_area("JSON", value="No JSON returned", height=120, key=key)
        return
    st.text_area("JSON", value=pretty_json(data), height=height, key=key)


def render_call_block(title: str, data: Any, metrics: Dict[str, Any], extra_time_ms: Optional[float] = None, json_key: str = "json"):
    st.subheader(title)
    st.write(f"URL: {metrics.get('url')}")
    st.write(f"Status: {metrics.get('status_code')}  |  OK: {metrics.get('ok')}")
    st.write(f"API time: {format_duration(metrics.get('elapsed_ms', 0.0))}")
    if extra_time_ms is not None:
        st.write(f"Filter time: {format_duration(extra_time_ms)}")
        st.write(f"API plus filter: {format_duration(metrics.get('elapsed_ms', 0.0) + extra_time_ms)}")
    st.write(f"Response size: {metrics.get('bytes', 0)} bytes")

    if metrics.get("error"):
        st.text_area("Error", value=str(metrics["error"]), height=140, key=f"{json_key}_err")

    render_json_textarea(key=json_key, data=data, height=340)

    if data is not None:
        st.download_button(
            "Download JSON",
            data=pretty_json(data).encode("utf-8"),
            file_name=f"{title.lower().replace(' ', '_')}.json",
            mime="application/json",
            key=f"{json_key}_dl",
        )


def get_secret(key: str, default: str = "") -> str:
    if key in st.secrets:
        val = st.secrets.get(key)
        return str(val).strip() if val is not None else default
    return os.getenv(key, default).strip()


def build_proxy_headers(api_key: str) -> Dict[str, str]:
    if not api_key:
        return {}
    return {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def proxy_make_url(base: str, path: str, email: str, extra_query: str) -> str:
    email_q = quote_plus(email.strip())
    extra = extra_query.strip()
    if extra:
        return f"{base}{path}?email={email_q}&{extra}"
    return f"{base}{path}?email={email_q}"


def wc_make_url(base: str, path: str, query: str) -> str:
    q = query.strip()
    if q:
        return f"{base}{path}?{q}"
    return f"{base}{path}"


def connection_check_proxy(proxy_base: str, proxy_api_key: str, timeout_s: float, verify_tls: bool) -> Dict[str, Any]:
    headers = build_proxy_headers(proxy_api_key)
    _, m1 = timed_get(f"{proxy_base}/", {}, timeout_s, verify_tls)
    _, m2 = timed_get(f"{proxy_base}/api/woocommerce/orders", headers, timeout_s, verify_tls)
    return {"base": m1, "auth_probe": m2}


def connection_check_wc(wc_base: str, ck: str, cs: str, timeout_s: float, verify_tls: bool) -> Dict[str, Any]:
    auth = (ck, cs)
    _, m1 = timed_get(f"{wc_base}/", {}, timeout_s, verify_tls)
    probe = wc_make_url(wc_base, "/wp-json/wc/v3/system_status", "")
    _, m2 = timed_get(probe, {"Accept": "application/json"}, timeout_s, verify_tls, auth=auth)
    return {"base": m1, "auth_probe": m2}


from urllib.parse import quote_plus
from typing import Any, Dict, List, Optional, Tuple

def wc_get_customer_id_by_email(
    wc_base: str,
    ck: str,
    cs: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
) -> Tuple[Optional[int], Dict[str, Any], Any]:
    auth = (ck, cs)
    url = f"{wc_base.rstrip('/')}/wp-json/wc/v3/customers?email={quote_plus(email.strip())}&per_page=10"
    data, metrics = timed_get_json(url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)

    customer_id = None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        cid = data[0].get("id")
        if isinstance(cid, int):
            customer_id = cid
    return customer_id, metrics, data


def wc_fetch_orders_by_email_fallback(
    wc_base: str,
    ck: str,
    cs: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
    per_page: int = 100,
) -> Tuple[Any, Dict[str, Any]]:
    auth = (ck, cs)
    url = f"{wc_base.rstrip('/')}/wp-json/wc/v3/orders?search={quote_plus(email.strip())}&per_page={per_page}&orderby=date&order=desc"
    data, metrics = timed_get_json(url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)

    if not isinstance(data, list):
        return data, metrics

    email_l = email.strip().lower()
    filtered = []
    for o in data:
        if not isinstance(o, dict):
            continue
        b = o.get("billing") or {}
        b_email = (b.get("email") or "").strip().lower()
        if b_email == email_l:
            filtered.append(o)

    return filtered, metrics


def wc_fetch_subscriptions_by_email_fallback(
    wc_base: str,
    ck: str,
    cs: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
    per_page: int = 100,
) -> Tuple[Any, Dict[str, Any]]:
    auth = (ck, cs)
    url = f"{wc_base.rstrip('/')}/wp-json/wc/v1/subscriptions?search={quote_plus(email.strip())}&per_page={per_page}&orderby=date&order=desc"
    data, metrics = timed_get_json(url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)

    if not isinstance(data, list):
        return data, metrics

    email_l = email.strip().lower()
    filtered = []
    for s in data:
        if not isinstance(s, dict):
            continue
        b = s.get("billing") or {}
        b_email = (b.get("email") or "").strip().lower()
        if b_email == email_l:
            filtered.append(s)

    return filtered, metrics


def wc_fetch_orders_and_subs_for_email(
    wc_base: str,
    ck: str,
    cs: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
    extra_query: str,
) -> Dict[str, Any]:
    auth = (ck, cs)

    customer_id, cust_metrics, cust_payload = wc_get_customer_id_by_email(
        wc_base, ck, cs, email, timeout_s, verify_tls
    )

    if customer_id:
        orders_url = f"{wc_base.rstrip('/')}/wp-json/wc/v3/orders?customer={customer_id}"
        if extra_query.strip():
            orders_url += f"&{extra_query.strip()}"
        orders_json, orders_metrics = timed_get_json(orders_url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)

        subs_url = f"{wc_base.rstrip('/')}/wp-json/wc/v1/subscriptions?customer={customer_id}"
        if extra_query.strip():
            subs_url += f"&{extra_query.strip()}"
        subs_json, subs_metrics = timed_get_json(subs_url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)

        return {
            "customer_lookup": {"data": cust_payload, "metrics": cust_metrics, "customer_id": customer_id},
            "orders": {"data": orders_json, "metrics": orders_metrics},
            "subscriptions": {"data": subs_json, "metrics": subs_metrics},
            "used_fallback": False,
        }

    orders_json, orders_metrics = wc_fetch_orders_by_email_fallback(
        wc_base, ck, cs, email, timeout_s, verify_tls
    )
    subs_json, subs_metrics = wc_fetch_subscriptions_by_email_fallback(
        wc_base, ck, cs, email, timeout_s, verify_tls
    )

    return {
        "customer_lookup": {"data": cust_payload, "metrics": cust_metrics, "customer_id": None},
        "orders": {"data": orders_json, "metrics": orders_metrics},
        "subscriptions": {"data": subs_json, "metrics": subs_metrics},
        "used_fallback": True,
    }
    
def run_proxy(email: str, proxy_base: str, proxy_api_key: str, timeout_s: float, verify_tls: bool, extra_query: str, manual_sid: str, mode: str) -> Dict[str, Any]:
    headers = build_proxy_headers(proxy_api_key)

    orders_url = proxy_make_url(proxy_base, "/api/woocommerce/orders", email, extra_query)
    subs_url = proxy_make_url(proxy_base, "/api/woocommerce/subscriptions", email, extra_query)

    orders_json, orders_metrics = timed_get_json(orders_url, headers, timeout_s, verify_tls)
    subs_json, subs_metrics = timed_get_json(subs_url, headers, timeout_s, verify_tls)

    if manual_sid.strip().isdigit():
        sub_ids = [int(manual_sid.strip())]
    else:
        sub_ids = collect_subscription_ids(subs_json)

    if mode == "required":
        t0 = time.perf_counter_ns()
        subs_out = filter_subscriptions_payload(subs_json)
        t1 = time.perf_counter_ns()
        subs_filter_ms = (t1 - t0) / 1_000_000.0

        t0 = time.perf_counter_ns()
        orders_out = filter_orders_payload(orders_json)
        t1 = time.perf_counter_ns()
        orders_filter_ms = (t1 - t0) / 1_000_000.0
    else:
        subs_out = subs_json
        orders_out = orders_json
        subs_filter_ms = None
        orders_filter_ms = None

    sub_orders = []
    for sid in sub_ids:
        so_url = proxy_make_url(proxy_base, f"/api/woocommerce/subscriptions/{sid}/orders", email, extra_query)
        so_json, so_metrics = timed_get_json(so_url, headers, timeout_s, verify_tls)

        if mode == "required":
            t0 = time.perf_counter_ns()
            so_out = filter_orders_payload(so_json)
            t1 = time.perf_counter_ns()
            so_filter_ms = (t1 - t0) / 1_000_000.0
        else:
            so_out = so_json
            so_filter_ms = None

        sub_orders.append(
            {
                "subscription_id": sid,
                "data": so_out,
                "metrics": so_metrics,
                "filter_ms": so_filter_ms,
            }
        )

    return {
        "orders": {"data": orders_out, "metrics": orders_metrics, "filter_ms": orders_filter_ms},
        "subscriptions": {"data": subs_out, "metrics": subs_metrics, "filter_ms": subs_filter_ms},
        "subscription_ids": sub_ids,
        "subscription_orders": sub_orders,
    }


def run_wc(email: str, wc_base: str, ck: str, cs: str, timeout_s: float, verify_tls: bool, extra_query: str, manual_sid: str, mode: str) -> Dict[str, Any]:
    auth = (ck, cs)

    customer_id, cust_metrics, cust_payload = wc_get_customer_id_by_email(wc_base, ck, cs, email, timeout_s, verify_tls)
    if not customer_id:
        return {
            "customer_lookup": {"data": cust_payload, "metrics": cust_metrics},
            "orders": {"data": None, "metrics": {"ok": False, "status_code": None, "elapsed_ms": 0.0, "bytes": 0, "url": "", "error": "No customer id found for this email"}, "filter_ms": None},
            "subscriptions": {"data": None, "metrics": {"ok": False, "status_code": None, "elapsed_ms": 0.0, "bytes": 0, "url": "", "error": "No customer id found for this email"}, "filter_ms": None},
            "subscription_ids": [],
            "subscription_orders": [],
        }

    orders_q = f"customer={customer_id}"
    if extra_query.strip():
        orders_q = f"{orders_q}&{extra_query.strip()}"
    orders_url = wc_make_url(wc_base, "/wp-json/wc/v3/orders", orders_q)
    orders_json, orders_metrics = timed_get_json(orders_url, {"Accept": "application/json"}, timeout_s, verify_tls, auth=auth)

    subs_q = f"customer={customer_id}"
    if extra_query.strip():
        subs_q = f"{subs_q}&{extra_query.strip()}"
    subs_url = wc_make_url(wc_base, "/wp-json/wc/v1/subscriptions", subs_q)
    subs_json, subs_metrics = timed_get_json(subs_url, {"Accept": "application/json"}, timeout_s, verify_tls, auth=auth)

    if manual_sid.strip().isdigit():
        sub_ids = [int(manual_sid.strip())]
    else:
        sub_ids = collect_subscription_ids(subs_json)

    if mode == "required":
        t0 = time.perf_counter_ns()
        subs_out = filter_subscriptions_payload(subs_json)
        t1 = time.perf_counter_ns()
        subs_filter_ms = (t1 - t0) / 1_000_000.0

        t0 = time.perf_counter_ns()
        orders_out = filter_orders_payload(orders_json)
        t1 = time.perf_counter_ns()
        orders_filter_ms = (t1 - t0) / 1_000_000.0
    else:
        subs_out = subs_json
        orders_out = orders_json
        subs_filter_ms = None
        orders_filter_ms = None

    sub_orders = []
    for sid in sub_ids:
        so_url = wc_make_url(wc_base, f"/wp-json/wc/v1/subscriptions/{sid}/orders", extra_query.strip())
        so_json, so_metrics = timed_get_json(so_url, {"Accept": "application/json"}, timeout_s, verify_tls, auth=auth)

        if mode == "required":
            t0 = time.perf_counter_ns()
            so_out = filter_orders_payload(so_json)
            t1 = time.perf_counter_ns()
            so_filter_ms = (t1 - t0) / 1_000_000.0
        else:
            so_out = so_json
            so_filter_ms = None

        sub_orders.append(
            {
                "subscription_id": sid,
                "data": so_out,
                "metrics": so_metrics,
                "filter_ms": so_filter_ms,
            }
        )

    return {
        "customer_lookup": {"data": cust_payload, "metrics": cust_metrics, "customer_id": customer_id},
        "orders": {"data": orders_out, "metrics": orders_metrics, "filter_ms": orders_filter_ms},
        "subscriptions": {"data": subs_out, "metrics": subs_metrics, "filter_ms": subs_filter_ms},
        "subscription_ids": sub_ids,
        "subscription_orders": sub_orders,
    }


def main():
    st.set_page_config(page_title="Woo API Speed Tester", layout="wide")
    st.title("Woo API Speed Tester")

    proxy_base = get_secret("PROXY_BASE_URL", "https://appanel.alternatehealthclub.com").rstrip("/")
    proxy_api_key = get_secret("PROXY_API_KEY", "")
    wc_base = get_secret("WC_BASE_URL", "https://alternatehealthclub.com").rstrip("/")
    wc_ck = get_secret("WC_CONSUMER_KEY", "")
    wc_cs = get_secret("WC_CONSUMER_SECRET", "")

    verify_tls = get_secret("VERIFY_TLS", "true").lower() not in ("0", "false", "no")
    default_timeout = float(get_secret("TIMEOUT_SECONDS", "60"))

    if "connected" not in st.session_state:
        st.session_state.connected = False
    if "connect_report" not in st.session_state:
        st.session_state.connect_report = None
    if "method" not in st.session_state:
        st.session_state.method = "Proxy App Panel"

    with st.sidebar:
        st.header("Settings")

        st.session_state.method = st.selectbox(
            "Fetch method",
            ["Proxy App Panel", "Direct WooCommerce"],
            index=0 if st.session_state.method == "Proxy App Panel" else 1,
            key="method_selectbox",
        )

        timeout_s = st.number_input(
            "Request timeout seconds",
            min_value=5.0,
            max_value=300.0,
            value=default_timeout,
            step=5.0,
        )

        extra_query = st.text_input(
            "Extra query params",
            value="per_page=100",
        )

        manual_sid = st.text_input(
            "Optional subscription id override",
            value="",
        )

        st.divider()
        st.subheader("Connection")

        creds_ok = True
        if st.session_state.method == "Proxy App Panel":
            st.write(f"Proxy base: {proxy_base}")
            if not proxy_api_key:
                creds_ok = False
                st.error("PROXY_API_KEY missing")
        else:
            st.write(f"Woo base: {wc_base}")
            if not wc_ck or not wc_cs:
                creds_ok = False
                st.error("WC_CONSUMER_KEY or WC_CONSUMER_SECRET missing")

        if st.button("Connect to API server", disabled=not creds_ok):
            if st.session_state.method == "Proxy App Panel":
                report = connection_check_proxy(proxy_base, proxy_api_key, timeout_s, verify_tls)
                base_ok = bool(report["base"].get("ok"))
                auth_ok = bool(report["auth_probe"].get("ok")) and report["auth_probe"].get("status_code") not in (401, 403)
                st.session_state.connected = base_ok and auth_ok
                st.session_state.connect_report = report
            else:
                report = connection_check_wc(wc_base, wc_ck, wc_cs, timeout_s, verify_tls)
                base_ok = bool(report["base"].get("ok"))
                auth_ok = bool(report["auth_probe"].get("ok")) and report["auth_probe"].get("status_code") not in (401, 403)
                st.session_state.connected = base_ok and auth_ok
                st.session_state.connect_report = report

        if st.session_state.connected:
            st.success("Connected")
        else:
            st.warning("Not connected yet")

        if st.session_state.connect_report:
            with st.expander("Connection debug details"):
                st.json(st.session_state.connect_report)

    if not st.session_state.connected:
        st.info("Connect first using the sidebar button. After Connected appears, run the tests.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.header("Full fetch mode")
        email_full = st.text_input("Customer email", key="email_full", placeholder="name@example.com")
        run_full = st.button("Run full fetch", key="run_full")

        if run_full:
            if not email_full.strip():
                st.error("Enter email first.")
            else:
                if st.session_state.method == "Proxy App Panel":
                    results = run_proxy(email_full, proxy_base, proxy_api_key, timeout_s, verify_tls, extra_query, manual_sid, mode="full")
                    st.write(f"Subscription ids found: {results['subscription_ids']}")
                    render_call_block("Orders full", results["orders"]["data"], results["orders"]["metrics"], json_key="full_orders")
                    render_call_block("Subscriptions full", results["subscriptions"]["data"], results["subscriptions"]["metrics"], json_key="full_subs")
                    st.subheader("Subscription id orders full")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found or returned, third endpoint skipped.")
                    for i, entry in enumerate(results["subscription_orders"], start=1):
                        render_call_block(
                            f"Subscription {entry['subscription_id']} orders full",
                            entry["data"],
                            entry["metrics"],
                            json_key=f"full_sub_orders_{i}",
                        )
                else:
                    results = run_wc(email_full, wc_base, wc_ck, wc_cs, timeout_s, verify_tls, extra_query, manual_sid, mode="full")
                    render_call_block("Customer lookup", results["customer_lookup"]["data"], results["customer_lookup"]["metrics"], json_key="full_customer")
                    if "customer_id" in results["customer_lookup"]:
                        st.write(f"Resolved Woo customer id: {results['customer_lookup']['customer_id']}")
                    st.write(f"Subscription ids found: {results['subscription_ids']}")
                    render_call_block("Orders full", results["orders"]["data"], results["orders"]["metrics"], json_key="full_orders")
                    render_call_block("Subscriptions full", results["subscriptions"]["data"], results["subscriptions"]["metrics"], json_key="full_subs")
                    st.subheader("Subscription id orders full")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found or returned, third endpoint skipped.")
                    for i, entry in enumerate(results["subscription_orders"], start=1):
                        render_call_block(
                            f"Subscription {entry['subscription_id']} orders full",
                            entry["data"],
                            entry["metrics"],
                            json_key=f"full_sub_orders_{i}",
                        )

    with col2:
        st.header("Required fields mode")
        email_req = st.text_input("Customer email", key="email_req", placeholder="name@example.com")
        run_req = st.button("Run required fields", key="run_req")

        if run_req:
            if not email_req.strip():
                st.error("Enter email first.")
            else:
                if st.session_state.method == "Proxy App Panel":
                    results = run_proxy(email_req, proxy_base, proxy_api_key, timeout_s, verify_tls, extra_query, manual_sid, mode="required")
                    st.write(f"Subscription ids found: {results['subscription_ids']}")

                    render_call_block(
                        "Orders required",
                        results["orders"]["data"],
                        results["orders"]["metrics"],
                        extra_time_ms=results["orders"]["filter_ms"],
                        json_key="req_orders",
                    )
                    render_call_block(
                        "Subscriptions required",
                        results["subscriptions"]["data"],
                        results["subscriptions"]["metrics"],
                        extra_time_ms=results["subscriptions"]["filter_ms"],
                        json_key="req_subs",
                    )

                    st.subheader("Subscription id orders required")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found or returned, third endpoint skipped.")
                    for i, entry in enumerate(results["subscription_orders"], start=1):
                        render_call_block(
                            f"Subscription {entry['subscription_id']} orders required",
                            entry["data"],
                            entry["metrics"],
                            extra_time_ms=entry["filter_ms"],
                            json_key=f"req_sub_orders_{i}",
                        )
                else:
                    results = run_wc(email_req, wc_base, wc_ck, wc_cs, timeout_s, verify_tls, extra_query, manual_sid, mode="required")
                    render_call_block("Customer lookup", results["customer_lookup"]["data"], results["customer_lookup"]["metrics"], json_key="req_customer")
                    if "customer_id" in results["customer_lookup"]:
                        st.write(f"Resolved Woo customer id: {results['customer_lookup']['customer_id']}")

                    st.write(f"Subscription ids found: {results['subscription_ids']}")

                    render_call_block(
                        "Orders required",
                        results["orders"]["data"],
                        results["orders"]["metrics"],
                        extra_time_ms=results["orders"]["filter_ms"],
                        json_key="req_orders",
                    )
                    render_call_block(
                        "Subscriptions required",
                        results["subscriptions"]["data"],
                        results["subscriptions"]["metrics"],
                        extra_time_ms=results["subscriptions"]["filter_ms"],
                        json_key="req_subs",
                    )

                    st.subheader("Subscription id orders required")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found or returned, third endpoint skipped.")
                    for i, entry in enumerate(results["subscription_orders"], start=1):
                        render_call_block(
                            f"Subscription {entry['subscription_id']} orders required",
                            entry["data"],
                            entry["metrics"],
                            extra_time_ms=entry["filter_ms"],
                            json_key=f"req_sub_orders_{i}",
                        )


if __name__ == "__main__":
    main()
