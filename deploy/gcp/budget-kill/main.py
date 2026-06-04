# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# Cloud Function (gen2, Pub/Sub-triggered) that hard-stops all GCP spend by
# detaching the billing account from the project once actual cost reaches the
# budget amount. Wired to the `kb-hard-cap-275usd` budget via the
# `billing-alerts` Pub/Sub topic. Belt-and-suspenders over the free-trial
# auto-pause at the full credit. See the GCP deploy spec, §5.1.
import base64
import json
import os

import functions_framework
from googleapiclient import discovery

PROJECT_ID = os.environ["PROJECT_ID"]
PROJECT_NAME = f"projects/{PROJECT_ID}"


@functions_framework.cloud_event
def stop_billing(cloud_event):
    message = cloud_event.data["message"]
    payload = base64.b64decode(message["data"]).decode("utf-8")
    data = json.loads(payload)

    cost = float(data.get("costAmount", 0))
    budget = float(data.get("budgetAmount", 0))
    print(f"budget notification: cost={cost} budget={budget} currency={data.get('currencyCode')}")

    if budget <= 0 or cost < budget:
        print("under budget; no action")
        return

    billing = discovery.build("cloudbilling", "v1", cache_discovery=False)
    info = billing.projects().getBillingInfo(name=PROJECT_NAME).execute()
    if not info.get("billingEnabled"):
        print("billing already disabled; no action")
        return

    result = billing.projects().updateBillingInfo(
        name=PROJECT_NAME, body={"billingAccountName": ""}
    ).execute()
    print(f"BILLING DISABLED for {PROJECT_NAME} (cost {cost} >= budget {budget}): {result}")
