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


def format_duration_ms_s(elapsed_ms: float) -> str:
    return f"{elapsed_ms:.3f} ms | {elapsed_ms/1000.0:.3f} s"


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
            "ok": bool(resp.ok),
            "status_code": resp.status_code,
            "elapsed_ms": elapsed_ms,
            "elapsed_s": elapsed_ms / 1000.0,
            "bytes": len(resp.content) if resp.content is not None else 0,
            "url": url,
            "error": None,
        }
        if not resp.ok:
            metrics["error"] = resp.text[:3000]
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
        metrics["error"] = f"JSON decode failed: {e}. First 800 chars: {resp.text[:800]}"
        return None, metrics


def get_secret(key: str, default: str = "") -> str:
    if key in st.secrets:
        v = st.secrets.get(key)
        return str(v).strip() if v is not None else default
    return os.getenv(key, default).strip()


def build_proxy_headers(api_key: str) -> Dict[str, str]:
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


def normalize_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def safe_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def should_keep_meta_key(k: str) -> bool:
    if not isinstance(k, str):
        return False
    kk = k.strip().lower()
    if kk == "medication_schedule":
        return True
    if "tracking" in kk:
        return True
    if "shipment" in kk:
        return True
    if "fedex" in kk:
        return True
    if "pkgsend" in kk:
        return True
    return False


def filter_order_required(order: Dict[str, Any]) -> Dict[str, Any]:
    order = safe_dict(order)

    line_items_in = normalize_list(order.get("line_items"))
    line_items_out: List[Dict[str, Any]] = []
    for li in line_items_in:
        li = safe_dict(li)
        line_items_out.append(
            {
                "name": li.get("name"),
                "quantity": li.get("quantity"),
                "total": li.get("total"),
                "image": {"src": safe_dict(li.get("image")).get("src")},
            }
        )

    meta_in = normalize_list(order.get("meta_data"))
    meta_out: List[Dict[str, Any]] = []
    for m in meta_in:
        m = safe_dict(m)
        k = m.get("key")
        if isinstance(k, str) and should_keep_meta_key(k):
            meta_out.append({"key": k, "value": m.get("value")})

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


def filter_orders_required(payload: Any) -> Any:
    if isinstance(payload, list):
        return [filter_order_required(x) for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        return filter_order_required(payload)
    return payload


def filter_subscription_required(sub: Dict[str, Any]) -> Dict[str, Any]:
    sub = safe_dict(sub)

    billing = safe_dict(sub.get("billing"))
    shipping = safe_dict(sub.get("shipping"))

    line_items_in = normalize_list(sub.get("line_items"))
    line_items_out: List[Dict[str, Any]] = []
    for li in line_items_in:
        li = safe_dict(li)
        line_items_out.append(
            {
                "name": li.get("name"),
                "quantity": li.get("quantity"),
                "total": li.get("total"),
                "image": {"src": safe_dict(li.get("image")).get("src")},
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


def filter_subscriptions_required(payload: Any) -> Any:
    if isinstance(payload, list):
        return [filter_subscription_required(x) for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        return filter_subscription_required(payload)
    return payload


def collect_subscription_ids_from_payload(payload: Any) -> List[int]:
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
            for it in node:
                visit(it)

    visit(payload)

    uniq: List[int] = []
    seen = set()
    for x in found:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq


def render_call(title: str, data: Any, metrics: Dict[str, Any], filter_ms: Optional[float], json_key: str):
    st.subheader(title)
    st.write(f"Status: {metrics.get('status_code')} | OK: {metrics.get('ok')}")
    st.write(f"API time: {format_duration_ms_s(float(metrics.get('elapsed_ms', 0.0)))}")
    if filter_ms is not None:
        st.write(f"Filter time: {format_duration_ms_s(float(filter_ms))}")
        st.write(f"API plus filter: {format_duration_ms_s(float(metrics.get('elapsed_ms', 0.0)) + float(filter_ms))}")
    st.write(f"Bytes: {metrics.get('bytes')}")

    if metrics.get("url"):
        st.code(metrics["url"], language="text")

    if metrics.get("error"):
        st.text_area("Error", value=str(metrics["error"]), height=140, key=f"{json_key}_err")

    if data is None:
        st.text_area("JSON", value="No JSON returned", height=220, key=json_key)
        return

    st.text_area("JSON", value=pretty_json(data), height=360, key=json_key)

    st.download_button(
        "Download JSON",
        data=pretty_json(data).encode("utf-8"),
        file_name=f"{title.lower().replace(' ', '_')}.json",
        mime="application/json",
        key=f"{json_key}_dl",
    )


def proxy_connect_probe(
    proxy_base: str,
    proxy_api_key: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
) -> Dict[str, Any]:
    headers = build_proxy_headers(proxy_api_key)
    base_resp, base_metrics = timed_get(f"{proxy_base}/", {}, timeout_s, verify_tls)
    probe_url = proxy_make_url(proxy_base, "/api/woocommerce/orders", email, "per_page=1")
    probe_resp, probe_metrics = timed_get(probe_url, headers, timeout_s, verify_tls)
    return {"base": base_metrics, "probe": probe_metrics}


def wc_connect_probe(
    wc_base: str,
    ck: str,
    cs: str,
    timeout_s: float,
    verify_tls: bool,
) -> Dict[str, Any]:
    auth = (ck, cs)
    base_resp, base_metrics = timed_get(f"{wc_base}/", {}, timeout_s, verify_tls)
    probe = wc_make_url(wc_base, "/wp-json/wc/v3/system_status", "")
    probe_resp, probe_metrics = timed_get(probe, {"Accept": "application/json"}, timeout_s, verify_tls, auth=auth)
    return {"base": base_metrics, "probe": probe_metrics}


def wc_get_customer_by_email(
    wc_base: str,
    ck: str,
    cs: str,
    email: str,
    timeout_s: float,
    verify_tls: bool,
) -> Tuple[Optional[int], Any, Dict[str, Any]]:
    auth = (ck, cs)
    url = wc_make_url(
        wc_base,
        "/wp-json/wc/v3/customers",
        f"role=all&email={quote_plus(email.strip())}&per_page=10",
    )
    data, metrics = timed_get_json(url, {"Accept": "application/json"}, timeout_s, verify_tls, auth=auth)
    cid: Optional[int] = None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        v = data[0].get("id")
        if isinstance(v, int):
            cid = v
    metrics["url"] = url
    return cid, data, metrics


def run_proxy_flow(
    email: str,
    proxy_base: str,
    proxy_api_key: str,
    timeout_s: float,
    verify_tls: bool,
    extra_query: str,
    manual_sid: str,
    mode: str,
) -> Dict[str, Any]:
    headers = build_proxy_headers(proxy_api_key)

    orders_url = proxy_make_url(proxy_base, "/api/woocommerce/orders", email, extra_query)
    subs_url = proxy_make_url(proxy_base, "/api/woocommerce/subscriptions", email, extra_query)

    orders_json, orders_metrics = timed_get_json(orders_url, headers, timeout_s, verify_tls)
    subs_json, subs_metrics = timed_get_json(subs_url, headers, timeout_s, verify_tls)

    if manual_sid.strip().isdigit():
        sub_ids = [int(manual_sid.strip())]
    else:
        sub_ids = collect_subscription_ids_from_payload(subs_json)

    if mode == "required":
        t0 = time.perf_counter_ns()
        orders_out = filter_orders_required(orders_json)
        t1 = time.perf_counter_ns()
        orders_filter_ms = (t1 - t0) / 1_000_000.0

        t0 = time.perf_counter_ns()
        subs_out = filter_subscriptions_required(subs_json)
        t1 = time.perf_counter_ns()
        subs_filter_ms = (t1 - t0) / 1_000_000.0
    else:
        orders_out = orders_json
        subs_out = subs_json
        orders_filter_ms = None
        subs_filter_ms = None

    sub_orders: List[Dict[str, Any]] = []
    for sid in sub_ids:
        so_url = proxy_make_url(proxy_base, f"/api/woocommerce/subscriptions/{sid}/orders", email, extra_query)
        so_json, so_metrics = timed_get_json(so_url, headers, timeout_s, verify_tls)

        if mode == "required":
            t0 = time.perf_counter_ns()
            so_out = filter_orders_required(so_json)
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


def run_wc_flow(
    email: str,
    wc_base: str,
    ck: str,
    cs: str,
    timeout_s: float,
    verify_tls: bool,
    extra_query: str,
    manual_sid: str,
    mode: str,
) -> Dict[str, Any]:
    auth = (ck, cs)
    per_page = 100

    customer_id, cust_payload, cust_metrics = wc_get_customer_by_email(
        wc_base, ck, cs, email, timeout_s, verify_tls
    )

    orders_json = None
    orders_metrics: Dict[str, Any] = {"ok": False, "status_code": None, "elapsed_ms": 0.0, "bytes": 0, "url": "", "error": None}
    subs_json = None
    subs_metrics: Dict[str, Any] = {"ok": False, "status_code": None, "elapsed_ms": 0.0, "bytes": 0, "url": "", "error": None}

    if customer_id is not None:
        q_orders = f"customer={customer_id}&per_page={per_page}"
        if extra_query.strip():
            q_orders = f"{q_orders}&{extra_query.strip()}"
        orders_url = wc_make_url(wc_base, "/wp-json/wc/v3/orders", q_orders)
        orders_json, orders_metrics = timed_get_json(orders_url, {"Accept": "application/json"}, timeout_s, verify_tls, auth=auth)

        q_subs = f"customer={customer_id}&per_page={per_page}"
        if extra_query.strip():
            q_subs = f"{q_subs}&{extra_query.strip()}"
        subs_url = wc_make_url(wc_base, "/wp-json/wc/v1/subscriptions", q_subs)
        subs_json, subs_metrics = timed_get_json(subs_url, {"Accept": "application/json"}, timeout_s, verify_tls, auth=auth)
    else:
        orders_metrics["error"] = "No Woo customer id found for this email. Orders fetch by customer id skipped."
        subs_metrics["error"] = "No Woo customer id found for this email. Subscriptions fetch by customer id skipped."

    if manual_sid.strip().isdigit():
        sub_ids = [int(manual_sid.strip())]
    else:
        sub_ids = collect_subscription_ids_from_payload(subs_json)

    if mode == "required":
        t0 = time.perf_counter_ns()
        orders_out = filter_orders_required(orders_json)
        t1 = time.perf_counter_ns()
        orders_filter_ms = (t1 - t0) / 1_000_000.0

        t0 = time.perf_counter_ns()
        subs_out = filter_subscriptions_required(subs_json)
        t1 = time.perf_counter_ns()
        subs_filter_ms = (t1 - t0) / 1_000_000.0
    else:
        orders_out = orders_json
        subs_out = subs_json
        orders_filter_ms = None
        subs_filter_ms = None

    sub_orders: List[Dict[str, Any]] = []
    for sid in sub_ids:
        so_url = wc_make_url(wc_base, f"/wp-json/wc/v1/subscriptions/{sid}/orders", f"per_page={per_page}")
        so_json, so_metrics = timed_get_json(so_url, {"Accept": "application/json"}, timeout_s, verify_tls, auth=auth)

        if mode == "required":
            t0 = time.perf_counter_ns()
            so_out = filter_orders_required(so_json)
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
        "customer_lookup": {"customer_id": customer_id, "data": cust_payload, "metrics": cust_metrics},
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

    if "fetch_method" not in st.session_state:
        st.session_state.fetch_method = "Proxy App Panel"
    if "connected" not in st.session_state:
        st.session_state.connected = False
    if "connect_report" not in st.session_state:
        st.session_state.connect_report = None

    with st.sidebar:
        st.header("Settings")

        st.session_state.fetch_method = st.selectbox(
            "Fetch method",
            ["Proxy App Panel", "Direct WooCommerce"],
            index=0 if st.session_state.fetch_method == "Proxy App Panel" else 1,
            key="fetch_method_select",
        )

        timeout_s = st.number_input(
            "Request timeout seconds",
            min_value=5.0,
            max_value=300.0,
            value=float(default_timeout),
            step=5.0,
        )

        extra_query = st.text_input(
            "Extra query params",
            value="per_page=100",
            help="Applied to proxy calls, applied to direct calls where valid",
        )

        manual_sid = st.text_input(
            "Optional subscription id override",
            value="",
            help="If subscription id extraction fails, paste a subscription id here",
        )

        st.divider()
        st.subheader("Connection")

        creds_ok = True
        proxy_test_email = ""
        if st.session_state.fetch_method == "Proxy App Panel":
            st.write(f"Proxy base: {proxy_base}")
            proxy_test_email = st.text_input("Proxy test email", value="", help="Required for proxy connect probe")
            if not proxy_api_key:
                creds_ok = False
                st.error("PROXY_API_KEY missing")
            if not proxy_test_email.strip():
                creds_ok = False
                st.error("Proxy test email required")
        else:
            st.write(f"Woo base: {wc_base}")
            if not wc_ck or not wc_cs:
                creds_ok = False
                st.error("WC_CONSUMER_KEY or WC_CONSUMER_SECRET missing")

        if st.button("Connect to API server", disabled=not creds_ok):
            if st.session_state.fetch_method == "Proxy App Panel":
                report = proxy_connect_probe(proxy_base, proxy_api_key, proxy_test_email, timeout_s, verify_tls)
            else:
                report = wc_connect_probe(wc_base, wc_ck, wc_cs, timeout_s, verify_tls)

            base_ok = bool(report["base"].get("ok"))
            probe_ok = bool(report["probe"].get("ok")) and report["probe"].get("status_code") not in (401, 403)
            st.session_state.connected = base_ok and probe_ok
            st.session_state.connect_report = report

        if st.session_state.connected:
            st.success("Connected")
        else:
            st.warning("Not connected")

        if st.session_state.connect_report:
            with st.expander("Connection debug details"):
                st.json(st.session_state.connect_report)

    if not st.session_state.connected:
        st.info("Connect first using the sidebar. After Connected appears, run tests.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.header("Full fetch")
        email_full = st.text_input("Customer email", key="email_full", placeholder="name@example.com")
        if st.button("Run full fetch", key="btn_full"):
            if not email_full.strip():
                st.error("Email required")
            else:
                if st.session_state.fetch_method == "Proxy App Panel":
                    results = run_proxy_flow(
                        email_full, proxy_base, proxy_api_key, timeout_s, verify_tls, extra_query, manual_sid, mode="full"
                    )
                    st.write(f"Subscription ids: {results['subscription_ids']}")
                    render_call("Orders full", results["orders"]["data"], results["orders"]["metrics"], None, "full_orders")
                    render_call("Subscriptions full", results["subscriptions"]["data"], results["subscriptions"]["metrics"], None, "full_subs")

                    st.subheader("Subscription orders full")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found, third endpoint not called")
                    for i, entry in enumerate(results["subscription_orders"], start=1):
                        render_call(
                            f"Subscription {entry['subscription_id']} orders full",
                            entry["data"],
                            entry["metrics"],
                            None,
                            f"full_sub_orders_{i}",
                        )
                else:
                    results = run_wc_flow(
                        email_full, wc_base, wc_ck, wc_cs, timeout_s, verify_tls, extra_query, manual_sid, mode="full"
                    )
                    st.write(f"Resolved customer id: {results['customer_lookup']['customer_id']}")
                    render_call("Customer lookup by email", results["customer_lookup"]["data"], results["customer_lookup"]["metrics"], None, "full_cust")
                    st.write(f"Subscription ids: {results['subscription_ids']}")
                    render_call("Orders full", results["orders"]["data"], results["orders"]["metrics"], None, "full_orders")
                    render_call("Subscriptions full", results["subscriptions"]["data"], results["subscriptions"]["metrics"], None, "full_subs")

                    st.subheader("Subscription orders full")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found, third endpoint not called")
                    for i, entry in enumerate(results["subscription_orders"], start=1):
                        render_call(
                            f"Subscription {entry['subscription_id']} orders full",
                            entry["data"],
                            entry["metrics"],
                            None,
                            f"full_sub_orders_{i}",
                        )

    with col2:
        st.header("Required fields only")
        email_req = st.text_input("Customer email", key="email_req", placeholder="name@example.com")
        if st.button("Run required fields", key="btn_req"):
            if not email_req.strip():
                st.error("Email required")
            else:
                if st.session_state.fetch_method == "Proxy App Panel":
                    results = run_proxy_flow(
                        email_req, proxy_base, proxy_api_key, timeout_s, verify_tls, extra_query, manual_sid, mode="required"
                    )
                    st.write(f"Subscription ids: {results['subscription_ids']}")
                    render_call("Orders required", results["orders"]["data"], results["orders"]["metrics"], results["orders"]["filter_ms"], "req_orders")
                    render_call("Subscriptions required", results["subscriptions"]["data"], results["subscriptions"]["metrics"], results["subscriptions"]["filter_ms"], "req_subs")

                    st.subheader("Subscription orders required")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found, third endpoint not called")
                    for i, entry in enumerate(results["subscription_orders"], start=1):
                        render_call(
                            f"Subscription {entry['subscription_id']} orders required",
                            entry["data"],
                            entry["metrics"],
                            entry["filter_ms"],
                            f"req_sub_orders_{i}",
                        )
                else:
                    results = run_wc_flow(
                        email_req, wc_base, wc_ck, wc_cs, timeout_s, verify_tls, extra_query, manual_sid, mode="required"
                    )
                    st.write(f"Resolved customer id: {results['customer_lookup']['customer_id']}")
                    render_call("Customer lookup by email", results["customer_lookup"]["data"], results["customer_lookup"]["metrics"], None, "req_cust")
                    st.write(f"Subscription ids: {results['subscription_ids']}")
                    render_call("Orders required", results["orders"]["data"], results["orders"]["metrics"], results["orders"]["filter_ms"], "req_orders")
                    render_call("Subscriptions required", results["subscriptions"]["data"], results["subscriptions"]["metrics"], results["subscriptions"]["filter_ms"], "req_subs")

                    st.subheader("Subscription orders required")
                    if not results["subscription_orders"]:
                        st.info("No subscription ids found, third endpoint not called")
                    for i, entry in enumerate(results["subscription_orders"], start=1):
                        render_call(
                            f"Subscription {entry['subscription_id']} orders required",
                            entry["data"],
                            entry["metrics"],
                            entry["filter_ms"],
                            f"req_sub_orders_{i}",
                        )


if __name__ == "__main__":
    main()
