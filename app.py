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
    """
    Works even if payload is wrapped or nested
    Looks for id and subscription_id keys anywhere
    """
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


def render_scrollable_json(title: str, data: Any, height: int = 320):
    st.write(title)
    if data is None:
        st.write("No JSON returned")
        return
    with st.container(height=height):
        st.code(pretty_json(data), language="json")


def render_call_block(
    title: str,
    data: Any,
    metrics: Dict[str, Any],
    extra_time_ms: Optional[float] = None,
):
    st.subheader(title)
    st.write(f"URL: {metrics.get('url')}")
    st.write(f"Status: {metrics.get('status_code')}  |  OK: {metrics.get('ok')}")
    st.write(f"API time: {format_duration(metrics.get('elapsed_ms', 0.0))}")
    if extra_time_ms is not None:
        st.write(f"Filter time: {format_duration(extra_time_ms)}")
        st.write(f"API plus filter: {format_duration(metrics.get('elapsed_ms', 0.0) + extra_time_ms)}")
    st.write(f"Response size: {metrics.get('bytes', 0)} bytes")

    if metrics.get("error"):
        with st.container(height=140):
            st.code(metrics["error"], language="text")

    render_scrollable_json("JSON", data, height=340)

    if data is not None:
        st.download_button(
            "Download JSON",
            data=pretty_json(data).encode("utf-8"),
            file_name=f"{title.lower().replace(' ', '_')}.json",
            mime="application/json",
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
        if extra.startswith("&"):
            return f"{base}{path}?email={email_q}{extra}"
        if extra.startswith("?"):
            return f"{base}{path}?email={email_q}&{extra[1:]}"
        return f"{base}{path}?email={email_q}&{extra}"
    return f"{base}{path}?email={email_q}"


def wc_url(base: str, path: str, extra_query: str) -> str:
    extra = extra_query.strip()
    if extra:
        if extra.startswith("&"):
            return f"{base}{path}?{extra[1:]}"
        if extra.startswith("?"):
            return f"{base}{path}{extra}"
        return f"{base}{path}?{extra}"
    return f"{base}{path}"


def wc_get_customer_id_by_email(
    wc_base: str,
    ck: str,
    cs: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
    per_page: int = 10,
) -> Tuple[Optional[int], Dict[str, Any], Optional[Any]]:
    auth = (ck, cs)
    url = wc_url(
        wc_base,
        "/wp-json/wc/v3/customers",
        f"email={quote_plus(email.strip())}&per_page={per_page}",
    )
    data, metrics = timed_get_json(url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)
    customer_id = None
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        cid = data[0].get("id")
        if isinstance(cid, int):
            customer_id = cid
    return customer_id, metrics, data


def connection_check_proxy(
    proxy_base: str,
    proxy_api_key: str,
    timeout_s: float,
    verify_tls: bool,
) -> Dict[str, Any]:
    headers = build_proxy_headers(proxy_api_key)

    base_url = f"{proxy_base}/"
    _, m1 = timed_get(base_url, headers={}, timeout_s=timeout_s, verify_tls=verify_tls)

    probe_url = f"{proxy_base}/api/woocommerce/orders"
    _, m2 = timed_get(probe_url, headers=headers, timeout_s=timeout_s, verify_tls=verify_tls)

    return {"base": m1, "auth_probe": m2}


def connection_check_wc(
    wc_base: str,
    ck: str,
    cs: str,
    timeout_s: float,
    verify_tls: bool,
) -> Dict[str, Any]:
    auth = (ck, cs)

    base_url = f"{wc_base}/"
    _, m1 = timed_get(base_url, headers={}, timeout_s=timeout_s, verify_tls=verify_tls)

    probe_url = wc_url(wc_base, "/wp-json/wc/v3/system_status", "")
    _, m2 = timed_get(probe_url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)

    return {"base": m1, "auth_probe": m2}


def run_proxy_full(
    proxy_base: str,
    proxy_api_key: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
    extra_query: str,
    manual_sid: str,
) -> Dict[str, Any]:
    headers = build_proxy_headers(proxy_api_key)

    orders_url = proxy_make_url(proxy_base, "/api/woocommerce/orders", email, extra_query)
    subs_url = proxy_make_url(proxy_base, "/api/woocommerce/subscriptions", email, extra_query)

    orders_json, orders_metrics = timed_get_json(orders_url, headers, timeout_s, verify_tls)
    subs_json, subs_metrics = timed_get_json(subs_url, headers, timeout_s, verify_tls)

    if manual_sid.strip().isdigit():
        sub_ids = [int(manual_sid.strip())]
    else:
        sub_ids = collect_subscription_ids(subs_json)

    sub_orders: List[Dict[str, Any]] = []
    for sid in sub_ids:
        so_url = proxy_make_url(proxy_base, f"/api/woocommerce/subscriptions/{sid}/orders", email, extra_query)
        so_json, so_metrics = timed_get_json(so_url, headers, timeout_s, verify_tls)
        sub_orders.append({"subscription_id": sid, "data": so_json, "metrics": so_metrics})

    return {
        "orders": {"data": orders_json, "metrics": orders_metrics},
        "subscriptions": {"data": subs_json, "metrics": subs_metrics},
        "subscription_ids": sub_ids,
        "subscription_orders": sub_orders,
    }


def run_proxy_required(
    proxy_base: str,
    proxy_api_key: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
    extra_query: str,
    manual_sid: str,
) -> Dict[str, Any]:
    headers = build_proxy_headers(proxy_api_key)

    subs_url = proxy_make_url(proxy_base, "/api/woocommerce/subscriptions", email, extra_query)
    subs_json, subs_metrics = timed_get_json(subs_url, headers, timeout_s, verify_tls)
    t0 = time.perf_counter_ns()
    subs_filtered = filter_subscriptions_payload(subs_json)
    t1 = time.perf_counter_ns()
    subs_filter_ms = (t1 - t0) / 1_000_000.0

    orders_url = proxy_make_url(proxy_base, "/api/woocommerce/orders", email, extra_query)
    orders_json, orders_metrics = timed_get_json(orders_url, headers, timeout_s, verify_tls)
    t0 = time.perf_counter_ns()
    orders_filtered = filter_orders_payload(orders_json)
    t1 = time.perf_counter_ns()
    orders_filter_ms = (t1 - t0) / 1_000_000.0

    if manual_sid.strip().isdigit():
        sub_ids = [int(manual_sid.strip())]
    else:
        sub_ids = collect_subscription_ids(subs_json)

    sub_orders: List[Dict[str, Any]] = []
    for sid in sub_ids:
        so_url = proxy_make_url(proxy_base, f"/api/woocommerce/subscriptions/{sid}/orders", email, extra_query)
        so_json, so_metrics = timed_get_json(so_url, headers, timeout_s, verify_tls)
        t0 = time.perf_counter_ns()
        so_filtered = filter_orders_payload(so_json)
        t1 = time.perf_counter_ns()
        so_filter_ms = (t1 - t0) / 1_000_000.0
        sub_orders.append(
            {
                "subscription_id": sid,
                "data": so_filtered,
                "metrics": so_metrics,
                "filter_elapsed_ms": so_filter_ms,
            }
        )

    return {
        "subscriptions": {"data": subs_filtered, "metrics": subs_metrics, "filter_ms": subs_filter_ms},
        "orders": {"data": orders_filtered, "metrics": orders_metrics, "filter_ms": orders_filter_ms},
        "subscription_ids": sub_ids,
        "subscription_orders": sub_orders,
    }


def run_wc_full(
    wc_base: str,
    ck: str,
    cs: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
    extra_query: str,
    manual_sid: str,
) -> Dict[str, Any]:
    auth = (ck, cs)

    customer_id, customer_metrics, customers_payload = wc_get_customer_id_by_email(
        wc_base, ck, cs, email, timeout_s, verify_tls
    )

    if not customer_id:
        return {
            "customer_lookup": {"data": customers_payload, "metrics": customer_metrics},
            "orders": {"data": None, "metrics": {"ok": False, "status_code": None, "elapsed_ms": 0.0, "bytes": 0, "url": "", "error": "No customer id found for this email"}},
            "subscriptions": {"data": None, "metrics": {"ok": False, "status_code": None, "elapsed_ms": 0.0, "bytes": 0, "url": "", "error": "No customer id found for this email"}},
            "subscription_ids": [],
            "subscription_orders": [],
        }

    orders_url = wc_url(wc_base, "/wp-json/wc/v3/orders", f"customer={customer_id}&{extra_query}" if extra_query else f"customer={customer_id}")
    orders_json, orders_metrics = timed_get_json(orders_url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)

    subs_url = wc_url(wc_base, "/wp-json/wc/v1/subscriptions", f"customer={customer_id}&{extra_query}" if extra_query else f"customer={customer_id}")
    subs_json, subs_metrics = timed_get_json(subs_url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)

    if manual_sid.strip().isdigit():
        sub_ids = [int(manual_sid.strip())]
    else:
        sub_ids = collect_subscription_ids(subs_json)

    sub_orders: List[Dict[str, Any]] = []
    for sid in sub_ids:
        so_url = wc_url(wc_base, f"/wp-json/wc/v1/subscriptions/{sid}/orders", extra_query)
        so_json, so_metrics = timed_get_json(so_url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)
        sub_orders.append({"subscription_id": sid, "data": so_json, "metrics": so_metrics})

    return {
        "customer_lookup": {"data": customers_payload, "metrics": customer_metrics, "customer_id": customer_id},
        "orders": {"data": orders_json, "metrics": orders_metrics},
        "subscriptions": {"data": subs_json, "metrics": subs_metrics},
        "subscription_ids": sub_ids,
        "subscription_orders": sub_orders,
    }


def run_wc_required(
    wc_base: str,
    ck: str,
    cs: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
    extra_query: str,
    manual_sid: str,
) -> Dict[str, Any]:
    auth = (ck, cs)

    customer_id, customer_metrics, customers_payload = wc_get_customer_id_by_email(
        wc_base, ck, cs, email, timeout_s, verify_tls
    )

    if not customer_id:
        return {
            "customer_lookup": {"data": customers_payload, "metrics": customer_metrics},
            "orders": {"data": None, "metrics": {"ok": False, "status_code": None, "elapsed_ms": 0.0, "bytes": 0, "url": "", "error": "No customer id found for this email"}},
            "subscriptions": {"data": None, "metrics": {"ok": False, "status_code": None, "elapsed_ms": 0.0, "bytes": 0, "url": "", "error": "No customer id found for this email"}},
            "subscription_ids": [],
            "subscription_orders": [],
        }

    subs_url = wc_url(wc_base, "/wp-json/wc/v1/subscriptions", f"customer={customer_id}&{extra_query}" if extra_query else f"customer={customer_id}")
    subs_json, subs_metrics = timed_get_json(subs_url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)
    t0 = time.perf_counter_ns()
    subs_filtered = filter_subscriptions_payload(subs_json)
    t1 = time.perf_counter_ns()
    subs_filter_ms = (t1 - t0) / 1_000_000.0

    orders_url = wc_url(wc_base, "/wp-json/wc/v3/orders", f"customer={customer_id}&{extra_query}" if extra_query else f"customer={customer_id}")
    orders_json, orders_metrics = timed_get_json(orders_url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)
    t0 = time.perf_counter_ns()
    orders_filtered = filter_orders_payload(orders_json)
    t1 = time.perf_counter_ns()
    orders_filter_ms = (t1 - t0) / 1_000_000.0

    if manual_sid.strip().isdigit():
        sub_ids = [int(manual_sid.strip())]
    else:
        sub_ids = collect_subscription_ids(subs_json)

    sub_orders: List[Dict[str, Any]] = []
    for sid in sub_ids:
        so_url = wc_url(wc_base, f"/wp-json/wc/v1/subscriptions/{sid}/orders", extra_query)
        so_json, so_metrics = timed_get_json(so_url, headers={"Accept": "application/json"}, timeout_s=timeout_s, verify_tls=verify_tls, auth=auth)
        t0 = time.perf_counter_ns()
        so_filtered = filter_orders_payload(so_json)
        t1 = time.perf_counter_ns()
        so_filter_ms = (t1 - t0) / 1_000_000.0
        sub_orders.append(
            {
                "subscription_id": sid,
                "data": so_filtered,
                "metrics": so_metrics,
                "filter_elapsed_ms": so_filter_ms,
            }
        )

    return {
        "customer_lookup": {"data": customers_payload, "metrics": customer_metrics, "customer_id": customer_id},
        "subscriptions": {"data": subs_filtered, "metrics": subs_metrics, "filter_ms": subs_filter_ms},
        "orders": {"data": orders_filtered, "metrics": orders_metrics, "filter_ms": orders_filter_ms},
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

    with st.sidebar:
        st.header("Settings")

        method = st.selectbox(
            "Fetch method",
            ["Proxy App Panel", "Direct WooCommerce"],
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
            help="Examples: per_page=100 or context=edit. This appends to direct endpoints and to proxy endpoints after email.",
        )

        manual_sid = st.text_input(
            "Optional subscription id override",
            value="",
            help="If your subscriptions payload does not contain ids, paste one id here to force the third endpoint to run.",
        )

        st.divider()
        st.subheader("Connection")

        creds_ok = True
        if method == "Proxy App Panel":
            st.write(f"Proxy base: {proxy_base}")
            if not proxy_api_key:
                creds_ok = False
                st.error("PROXY_API_KEY is missing in secrets or env")
        else:
            st.write(f"Woo base: {wc_base}")
            if not wc_ck or not wc_cs:
                creds_ok = False
                st.error("WC_CONSUMER_KEY or WC_CONSUMER_SECRET is missing in secrets or env")

        if st.button("Connect to API server", disabled=not creds_ok):
            if method == "Proxy App Panel":
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
        st.info("Use the sidebar Connect to API server button first. After Connected appears, run the tests.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.header("Full fetch mode")
        email_full = st.text_input("Customer email", key="email_full", placeholder="name@example.com")
        if st.button("Run full fetch", key="run_full"):
            if not email_full.strip():
                st.error("Enter email first.")
            else:
                if method == "Proxy App Panel":
                    results = run_proxy_full(proxy_base, proxy_api_key, email_full, timeout_s, verify_tls, extra_query, manual_sid)
                    render_call_block("Orders full", results["orders"]["data"], results["orders"]["metrics"])
                    render_call_block("Subscriptions full", results["subscriptions"]["data"], results["subscriptions"]["metrics"])
                    st.write(f"Subscription ids found: {results['subscription_ids']}")
                    st.subheader("Subscription id orders full")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found or returned, third endpoint skipped.")
                    for entry in results["subscription_orders"]:
                        render_call_block(
                            f"Subscription {entry['subscription_id']} orders full",
                            entry["data"],
                            entry["metrics"],
                        )
                else:
                    results = run_wc_full(wc_base, wc_ck, wc_cs, email_full, timeout_s, verify_tls, extra_query, manual_sid)
                    render_call_block("Customer lookup", results["customer_lookup"]["data"], results["customer_lookup"]["metrics"])
                    if "customer_id" in results["customer_lookup"]:
                        st.write(f"Resolved Woo customer id: {results['customer_lookup']['customer_id']}")
                    render_call_block("Orders full", results["orders"]["data"], results["orders"]["metrics"])
                    render_call_block("Subscriptions full", results["subscriptions"]["data"], results["subscriptions"]["metrics"])
                    st.write(f"Subscription ids found: {results['subscription_ids']}")
                    st.subheader("Subscription id orders full")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found or returned, third endpoint skipped.")
                    for entry in results["subscription_orders"]:
                        render_call_block(
                            f"Subscription {entry['subscription_id']} orders full",
                            entry["data"],
                            entry["metrics"],
                        )

    with col2:
        st.header("Required fields mode")
        email_req = st.text_input("Customer email", key="email_req", placeholder="name@example.com")
        if st.button("Run required fields", key="run_req"):
            if not email_req.strip():
                st.error("Enter email first.")
            else:
                if method == "Proxy App Panel":
                    results = run_proxy_required(proxy_base, proxy_api_key, email_req, timeout_s, verify_tls, extra_query, manual_sid)

                    render_call_block(
                        "Subscriptions required",
                        results["subscriptions"]["data"],
                        results["subscriptions"]["metrics"],
                        extra_time_ms=results["subscriptions"]["filter_ms"],
                    )

                    render_call_block(
                        "Orders required",
                        results["orders"]["data"],
                        results["orders"]["metrics"],
                        extra_time_ms=results["orders"]["filter_ms"],
                    )

                    st.write(f"Subscription ids found: {results['subscription_ids']}")
                    st.subheader("Subscription id orders required")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found or returned, third endpoint skipped.")
                    for entry in results["subscription_orders"]:
                        render_call_block(
                            f"Subscription {entry['subscription_id']} orders required",
                            entry["data"],
                            entry["metrics"],
                            extra_time_ms=entry["filter_elapsed_ms"],
                        )
                else:
                    results = run_wc_required(wc_base, wc_ck, wc_cs, email_req, timeout_s, verify_tls, extra_query, manual_sid)

                    render_call_block("Customer lookup", results["customer_lookup"]["data"], results["customer_lookup"]["metrics"])
                    if "customer_id" in results["customer_lookup"]:
                        st.write(f"Resolved Woo customer id: {results['customer_lookup']['customer_id']}")

                    render_call_block(
                        "Subscriptions required",
                        results["subscriptions"]["data"],
                        results["subscriptions"]["metrics"],
                        extra_time_ms=results["subscriptions"]["filter_ms"],
                    )

                    render_call_block(
                        "Orders required",
                        results["orders"]["data"],
                        results["orders"]["metrics"],
                        extra_time_ms=results["orders"]["filter_ms"],
                    )

                    st.write(f"Subscription ids found: {results['subscription_ids']}")
                    st.subheader("Subscription id orders required")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found or returned, third endpoint skipped.")
                    for entry in results["subscription_orders"]:
                        render_call_block(
                            f"Subscription {entry['subscription_id']} orders required",
                            entry["data"],
                            entry["metrics"],
                            extra_time_ms=entry["filter_elapsed_ms"],
                        )


if __name__ == "__main__":
    main()
