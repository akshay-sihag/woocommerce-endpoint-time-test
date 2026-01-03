import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple

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


def safe_get(d: Any, path: List[str], default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def timed_get_json(url: str, headers: Dict[str, str], timeout_s: float) -> Tuple[Optional[Any], Dict[str, Any]]:
    """
    Returns: (json_data_or_none, metrics)
    metrics includes:
      ok, status_code, elapsed_ms, elapsed_s, bytes, url, error
    """
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
            return None, metrics

        try:
            return resp.json(), metrics
        except Exception as e:
            metrics["ok"] = False
            metrics["error"] = f"JSON decode failed: {e}"
            return None, metrics

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


def format_duration(elapsed_ms: float) -> str:
    # exact ms plus seconds with 3 decimals
    return f"{elapsed_ms:.3f} ms  |  {elapsed_ms/1000.0:.3f} s"


def normalize_to_list(payload: Any) -> List[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    return [payload]


def filter_subscription_item(sub: Dict[str, Any]) -> Dict[str, Any]:
    # combines list plus details per your spec
    billing = safe_get(sub, ["billing"], {}) or {}
    shipping = safe_get(sub, ["shipping"], {}) or {}

    line_items_in = safe_get(sub, ["line_items"], []) or []
    line_items_out = []
    for li in normalize_to_list(line_items_in):
        if not isinstance(li, dict):
            continue
        li_out = {
            "name": li.get("name"),
            "quantity": li.get("quantity"),
            "total": li.get("total"),
            "image": {"src": safe_get(li, ["image", "src"])},
        }
        # For list view, quantity and total might be absent, still fine
        line_items_out.append(li_out)

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


def run_full_mode(email: str, timeout_s: float) -> Dict[str, Any]:
    headers = build_headers()
    results: Dict[str, Any] = {}

    orders_url = f"{APPANEL_BASE_URL}/api/woocommerce/orders?email={email}"
    subs_url = f"{APPANEL_BASE_URL}/api/woocommerce/subscriptions?email={email}"

    orders_json, orders_metrics = timed_get_json(orders_url, headers, timeout_s)
    results["orders_full"] = {"data": orders_json, "metrics": orders_metrics}

    subs_json, subs_metrics = timed_get_json(subs_url, headers, timeout_s)
    results["subscriptions_full"] = {"data": subs_json, "metrics": subs_metrics}

    sub_ids = collect_subscription_ids(subs_json)
    sub_orders_all: List[Dict[str, Any]] = []

    for sid in sub_ids:
        so_url = f"{APPANEL_BASE_URL}/api/woocommerce/subscriptions/{sid}/orders?email={email}"
        so_json, so_metrics = timed_get_json(so_url, headers, timeout_s)
        sub_orders_all.append({"subscription_id": sid, "data": so_json, "metrics": so_metrics})

    results["subscription_orders_full"] = sub_orders_all
    return results


def run_required_mode(email: str, timeout_s: float) -> Dict[str, Any]:
    headers = build_headers()
    results: Dict[str, Any] = {}

    orders_url = f"{APPANEL_BASE_URL}/api/woocommerce/orders?email={email}"
    subs_url = f"{APPANEL_BASE_URL}/api/woocommerce/subscriptions?email={email}"

    # Subscriptions fetch then filter
    subs_json, subs_metrics = timed_get_json(subs_url, headers, timeout_s)
    t0 = time.perf_counter_ns()
    subs_filtered = filter_subscriptions_payload(subs_json)
    t1 = time.perf_counter_ns()
    filter_ms = (t1 - t0) / 1_000_000.0
    results["subscriptions_required"] = {
        "data": subs_filtered,
        "metrics": subs_metrics,
        "filter_elapsed_ms": filter_ms,
        "total_elapsed_ms": subs_metrics["elapsed_ms"] + filter_ms,
    }

    # Orders fetch then filter
    orders_json, orders_metrics = timed_get_json(orders_url, headers, timeout_s)
    t0 = time.perf_counter_ns()
    orders_filtered = filter_orders_payload(orders_json)
    t1 = time.perf_counter_ns()
    filter_ms = (t1 - t0) / 1_000_000.0
    results["orders_required"] = {
        "data": orders_filtered,
        "metrics": orders_metrics,
        "filter_elapsed_ms": filter_ms,
        "total_elapsed_ms": orders_metrics["elapsed_ms"] + filter_ms,
    }

    # Subscription orders: need subscription ids from the full subscriptions response
    sub_ids = collect_subscription_ids(subs_json)
    sub_orders_all: List[Dict[str, Any]] = []

    for sid in sub_ids:
        so_url = f"{APPANEL_BASE_URL}/api/woocommerce/subscriptions/{sid}/orders?email={email}"
        so_json, so_metrics = timed_get_json(so_url, headers, timeout_s)
        t0 = time.perf_counter_ns()
        so_filtered = filter_orders_payload(so_json)
        t1 = time.perf_counter_ns()
        filter_ms = (t1 - t0) / 1_000_000.0
        sub_orders_all.append(
            {
                "subscription_id": sid,
                "data": so_filtered,
                "metrics": so_metrics,
                "filter_elapsed_ms": filter_ms,
                "total_elapsed_ms": so_metrics["elapsed_ms"] + filter_ms,
            }
        )

    results["subscription_orders_required"] = sub_orders_all
    return results


def render_endpoint_block(title: str, data: Any, metrics: Dict[str, Any], extra_time_ms: Optional[float] = None):
    st.subheader(title)

    ok = metrics.get("ok", False)
    status = metrics.get("status_code", None)
    elapsed_ms = metrics.get("elapsed_ms", 0.0)
    size_bytes = metrics.get("bytes", 0)

    st.write(f"Status: {status}  |  OK: {ok}")
    st.write(f"API time: {format_duration(elapsed_ms)}")
    if extra_time_ms is not None:
        st.write(f"Filter time: {format_duration(extra_time_ms)}")
        st.write(f"API plus filter: {format_duration(elapsed_ms + extra_time_ms)}")
    st.write(f"Response size: {size_bytes} bytes")
    if metrics.get("error"):
        st.code(metrics["error"], language="text")

    if data is not None:
        st.code(pretty_json(data), language="json")
        st.download_button(
            label="Download JSON",
            data=pretty_json(data).encode("utf-8"),
            file_name=f"{title.lower().replace(' ', '_')}.json",
            mime="application/json",
        )


def main():
    st.set_page_config(page_title="AHC WooCommerce API Timing Tester", layout="wide")
    st.title("AHC API Timing Tester for Orders and Subscriptions")

    if not APPANEL_API_KEY:
        st.warning("APPANEL_API_KEY is not set in environment variables. Requests will fail until you set it.")

    with st.sidebar:
        st.header("Settings")
        st.write(f"Base URL: {APPANEL_BASE_URL}")
        timeout_s = st.number_input("Request timeout seconds", min_value=5.0, max_value=300.0, value=DEFAULT_TIMEOUT_SECONDS, step=5.0)
        st.caption("Tip: For fair comparison, run multiple times and compare averages.")

    col1, col2 = st.columns(2)

    with col1:
        st.header("Full fetch mode")
        email_full = st.text_input("Customer email for full mode", key="email_full", placeholder="name@example.com")
        run_full = st.button("Run full fetch", key="run_full")
        if run_full:
            if not email_full.strip():
                st.error("Please enter an email.")
            else:
                with st.spinner("Calling endpoints in full mode..."):
                    results = run_full_mode(email_full.strip(), timeout_s)

                # Orders
                o = results["orders_full"]
                render_endpoint_block("Orders full", o["data"], o["metrics"])

                # Subscriptions
                s = results["subscriptions_full"]
                render_endpoint_block("Subscriptions full", s["data"], s["metrics"])

                # Subscription orders
                st.subheader("Subscription orders full")
                sub_orders = results["subscription_orders_full"]
                if not sub_orders:
                    st.info("No subscription ids found from subscriptions response, so no subscription orders calls were made.")
                for idx, entry in enumerate(sub_orders, start=1):
                    sid = entry["subscription_id"]
                    render_endpoint_block(f"Subscription {sid} orders full", entry["data"], entry["metrics"])

    with col2:
        st.header("Required fields mode")
        email_req = st.text_input("Customer email for required mode", key="email_req", placeholder="name@example.com")
        run_req = st.button("Run required fields", key="run_req")
        if run_req:
            if not email_req.strip():
                st.error("Please enter an email.")
            else:
                with st.spinner("Calling endpoints in required fields mode..."):
                    results = run_required_mode(email_req.strip(), timeout_s)

                # Subscriptions required
                sr = results["subscriptions_required"]
                render_endpoint_block(
                    "Subscriptions required",
                    sr["data"],
                    sr["metrics"],
                    extra_time_ms=sr["filter_elapsed_ms"],
                )

                # Orders required
                orq = results["orders_required"]
                render_endpoint_block(
                    "Orders required",
                    orq["data"],
                    orq["metrics"],
                    extra_time_ms=orq["filter_elapsed_ms"],
                )

                # Subscription orders required
                st.subheader("Subscription orders required")
                sub_orders = results["subscription_orders_required"]
                if not sub_orders:
                    st.info("No subscription ids found from subscriptions response, so no subscription orders calls were made.")
                for idx, entry in enumerate(sub_orders, start=1):
                    sid = entry["subscription_id"]
                    render_endpoint_block(
                        f"Subscription {sid} orders required",
                        entry["data"],
                        entry["metrics"],
                        extra_time_ms=entry["filter_elapsed_ms"],
                    )


if __name__ == "__main__":
    main()
