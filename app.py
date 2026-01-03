import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests
import streamlit as st


APPANEL_BASE_URL = os.getenv("APPANEL_BASE_URL", "https://appanel.alternatehealthclub.com").rstrip("/")
APPANEL_API_KEY = os.getenv("APPANEL_API_KEY", "").strip()

DEFAULT_TIMEOUT_SECONDS = float(os.getenv("APPANEL_TIMEOUT_SECONDS", "60"))
VERIFY_TLS = os.getenv("APPANEL_VERIFY_TLS", "true").strip().lower() not in ("0", "false", "no")


def build_headers() -> Dict[str, str]:
    if not APPANEL_API_KEY:
        return {}
    return {
        "X-API-Key": APPANEL_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def pretty_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def timed_get(url: str, headers: Dict[str, str], timeout_s: float) -> Tuple[Optional[requests.Response], Dict[str, Any]]:
    t0 = time.perf_counter_ns()
    try:
        resp = requests.get(url, headers=headers, timeout=timeout_s, verify=VERIFY_TLS)
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


def timed_get_json(url: str, headers: Dict[str, str], timeout_s: float) -> Tuple[Optional[Any], Dict[str, Any]]:
    resp, metrics = timed_get(url, headers, timeout_s)
    if resp is None or not metrics.get("ok"):
        return None, metrics
    try:
        return resp.json(), metrics
    except Exception as e:
        metrics["ok"] = False
        metrics["error"] = f"JSON decode failed: {e}. First 500 chars: {resp.text[:500]}"
        return None, metrics


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
        "id": sub.get("id"),
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


def collect_subscription_ids(subscriptions_payload: Any) -> List[int]:
    ids: List[int] = []
    if isinstance(subscriptions_payload, list):
        for s in subscriptions_payload:
            if isinstance(s, dict) and isinstance(s.get("id"), int):
                ids.append(s["id"])
    elif isinstance(subscriptions_payload, dict):
        sid = subscriptions_payload.get("id")
        if isinstance(sid, int):
            ids.append(sid)
    return ids


def make_url(path: str, email: str, extra_query: str) -> str:
    email_q = quote_plus(email.strip())
    extra = extra_query.strip()
    if extra:
        if extra.startswith("&"):
            return f"{APPANEL_BASE_URL}{path}?email={email_q}{extra}"
        if extra.startswith("?"):
            return f"{APPANEL_BASE_URL}{path}?email={email_q}&{extra[1:]}"
        return f"{APPANEL_BASE_URL}{path}?email={email_q}&{extra}"
    return f"{APPANEL_BASE_URL}{path}?email={email_q}"


def connection_check(timeout_s: float) -> Dict[str, Any]:
    """
    Step 1 checks the server is reachable
    Step 2 checks the API key is accepted by calling a protected endpoint without email
    """
    headers = build_headers()

    base_url = f"{APPANEL_BASE_URL}/"
    resp1, m1 = timed_get(base_url, {}, timeout_s)

    probe_url = f"{APPANEL_BASE_URL}/api/woocommerce/orders"
    resp2, m2 = timed_get(probe_url, headers, timeout_s)

    return {"base": m1, "auth_probe": m2}


def render_call_block(title: str, data: Any, metrics: Dict[str, Any], extra_time_ms: Optional[float] = None):
    st.subheader(title)

    st.write(f"URL: {metrics.get('url')}")
    st.write(f"Status: {metrics.get('status_code')}  |  OK: {metrics.get('ok')}")
    st.write(f"API time: {format_duration(metrics.get('elapsed_ms', 0.0))}")
    if extra_time_ms is not None:
        st.write(f"Filter time: {format_duration(extra_time_ms)}")
        st.write(f"API plus filter: {format_duration(metrics.get('elapsed_ms', 0.0) + extra_time_ms)}")
    st.write(f"Response size: {metrics.get('bytes', 0)} bytes")

    if metrics.get("error"):
        st.code(metrics["error"], language="text")

    if data is not None:
        st.code(pretty_json(data), language="json")
        st.download_button(
            "Download JSON",
            data=pretty_json(data).encode("utf-8"),
            file_name=f"{title.lower().replace(' ', '_')}.json",
            mime="application/json",
        )


def main():
    st.set_page_config(page_title="AHC API Timing Tester", layout="wide")
    st.title("AHC API Timing Tester")

    if "connected" not in st.session_state:
        st.session_state.connected = False
    if "last_connect_report" not in st.session_state:
        st.session_state.last_connect_report = None

    with st.sidebar:
        st.header("Settings")
        st.write(f"Base URL: {APPANEL_BASE_URL}")

        timeout_s = st.number_input(
            "Request timeout seconds",
            min_value=5.0,
            max_value=300.0,
            value=DEFAULT_TIMEOUT_SECONDS,
            step=5.0,
        )

        extra_query = st.text_input(
            "Extra query params (optional)",
            value="",
            help="Example: per_page=100 or context=edit. These will be appended to every endpoint call after email.",
        )

        st.divider()
        st.subheader("Connection")
        if not APPANEL_API_KEY:
            st.error("APPANEL_API_KEY env var is missing. Set it in Streamlit env variables.")
        else:
            if st.button("Connect to API server"):
                report = connection_check(timeout_s)
                st.session_state.last_connect_report = report

                base_ok = bool(report["base"].get("ok"))
                auth_ok = bool(report["auth_probe"].get("ok")) and report["auth_probe"].get("status_code") not in (401, 403)

                st.session_state.connected = base_ok and auth_ok

            if st.session_state.connected:
                st.success("Connected")
            else:
                st.warning("Not connected yet")

            if st.session_state.last_connect_report:
                with st.expander("Connection debug details", expanded=False):
                    st.write("Base reachability check")
                    st.json(st.session_state.last_connect_report["base"])
                    st.write("API key probe check")
                    st.json(st.session_state.last_connect_report["auth_probe"])

    if not st.session_state.connected:
        st.info("Step 1: Click Connect to API server in the sidebar. Only after it shows Connected the endpoint tests will run.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.header("Full fetch mode")
        email_full = st.text_input("Customer email", key="email_full", placeholder="name@example.com")
        if st.button("Run full fetch", key="run_full"):
            if not email_full.strip():
                st.error("Enter email first.")
            else:
                headers = build_headers()

                orders_url = make_url("/api/woocommerce/orders", email_full, extra_query)
                subs_url = make_url("/api/woocommerce/subscriptions", email_full, extra_query)

                with st.spinner("Calling orders full..."):
                    orders_json, orders_metrics = timed_get_json(orders_url, headers, timeout_s)
                render_call_block("Orders full", orders_json, orders_metrics)

                with st.spinner("Calling subscriptions full..."):
                    subs_json, subs_metrics = timed_get_json(subs_url, headers, timeout_s)
                render_call_block("Subscriptions full", subs_json, subs_metrics)

                sub_ids = collect_subscription_ids(subs_json)
                st.subheader("Subscription id orders full")
                if not sub_ids:
                    st.info("No subscription ids found in subscriptions response, so subscriptions id orders calls were skipped.")
                for sid in sub_ids:
                    so_url = make_url(f"/api/woocommerce/subscriptions/{sid}/orders", email_full, extra_query)
                    with st.spinner(f"Calling subscription {sid} orders full..."):
                        so_json, so_metrics = timed_get_json(so_url, headers, timeout_s)
                    render_call_block(f"Subscription {sid} orders full", so_json, so_metrics)

    with col2:
        st.header("Required fields mode")
        email_req = st.text_input("Customer email", key="email_req", placeholder="name@example.com")
        if st.button("Run required fields", key="run_req"):
            if not email_req.strip():
                st.error("Enter email first.")
            else:
                headers = build_headers()

                orders_url = make_url("/api/woocommerce/orders", email_req, extra_query)
                subs_url = make_url("/api/woocommerce/subscriptions", email_req, extra_query)

                with st.spinner("Calling subscriptions then filtering..."):
                    subs_json, subs_metrics = timed_get_json(subs_url, headers, timeout_s)
                    t0 = time.perf_counter_ns()
                    subs_filtered = filter_subscriptions_payload(subs_json)
                    t1 = time.perf_counter_ns()
                    filter_ms = (t1 - t0) / 1_000_000.0
                render_call_block("Subscriptions required", subs_filtered, subs_metrics, extra_time_ms=filter_ms)

                with st.spinner("Calling orders then filtering..."):
                    orders_json, orders_metrics = timed_get_json(orders_url, headers, timeout_s)
                    t0 = time.perf_counter_ns()
                    orders_filtered = filter_orders_payload(orders_json)
                    t1 = time.perf_counter_ns()
                    filter_ms = (t1 - t0) / 1_000_000.0
                render_call_block("Orders required", orders_filtered, orders_metrics, extra_time_ms=filter_ms)

                sub_ids = collect_subscription_ids(subs_json)
                st.subheader("Subscription id orders required")
                if not sub_ids:
                    st.info("No subscription ids found in subscriptions response, so subscriptions id orders calls were skipped.")
                for sid in sub_ids:
                    so_url = make_url(f"/api/woocommerce/subscriptions/{sid}/orders", email_req, extra_query)
                    with st.spinner(f"Calling subscription {sid} orders then filtering..."):
                        so_json, so_metrics = timed_get_json(so_url, headers, timeout_s)
                        t0 = time.perf_counter_ns()
                        so_filtered = filter_orders_payload(so_json)
                        t1 = time.perf_counter_ns()
                        filter_ms = (t1 - t0) / 1_000_000.0
                    render_call_block(f"Subscription {sid} orders required", so_filtered, so_metrics, extra_time_ms=filter_ms)


if __name__ == "__main__":
    main()
