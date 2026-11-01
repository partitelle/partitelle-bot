#!/usr/bin/env bash
# Wake the bot and run the payment reminders.
#
# Usage: JOBS_SECRET=... run-payment-reminders.sh <base-url>
# Env:   JOBS_SECRET     (required) bearer secret, same value as PB_JOBS_SECRET on the host; never printed
#        WARMUP_TIMEOUT  seconds to wait for GET /health to answer 200, default 300 (the free host may be asleep)
#        WARMUP_INTERVAL seconds between health checks, default 20
#        RETRY_DELAY     seconds between POST attempts, default 30 (3 attempts, only on 503 or no answer)
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: JOBS_SECRET=... $0 <base-url>" >&2
  exit 2
fi
: "${JOBS_SECRET:?JOBS_SECRET is not set}"

base_url="${1%/}"
warmup_timeout="${WARMUP_TIMEOUT:-300}"
warmup_interval="${WARMUP_INTERVAL:-20}"
retry_delay="${RETRY_DELAY:-30}"
body="$(mktemp)"
trap 'rm -f "$body"' EXIT

# Warm-up: 200 on /health means both the host and its database are awake.
deadline=$((SECONDS + warmup_timeout))
while true; do
  # Status 000 = no answer (connection error or timeout).
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 30 "${base_url}/health" || true)"
  if [ "$status" = "200" ]; then
    echo "Bot is up at ${base_url} (GET /health 200)"
    break
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "::error::${base_url}/health did not answer 200 within ${warmup_timeout}s (last status: ${status})."
    exit 1
  fi
  echo "GET /health answered ${status}, retrying in ${warmup_interval}s..."
  sleep "$warmup_interval"
done

# Run the reminders. Retry only on 503 or no answer; anything else is final.
for attempt in 1 2 3; do
  status="$(curl --silent --output "$body" --write-out '%{http_code}' --max-time 60 --request POST \
    --header "Authorization: Bearer ${JOBS_SECRET}" "${base_url}/jobs/payment-reminders" || true)"
  case "$status" in
    2*)
      echo "Payment reminders done (HTTP ${status}): $(cat "$body")"
      if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
        { echo "### Payment reminders"; echo; echo '```json'; cat "$body"; echo; echo '```'; } >>"$GITHUB_STEP_SUMMARY"
      fi
      exit 0
      ;;
    000 | 503)
      if [ "$attempt" -lt 3 ]; then
        echo "POST /jobs/payment-reminders answered ${status} (attempt ${attempt}/3), retrying in ${retry_delay}s..."
        sleep "$retry_delay"
        continue
      fi
      echo "::error::POST /jobs/payment-reminders still failing after 3 attempts (last status: ${status})."
      exit 1
      ;;
    404)
      echo "::error::POST /jobs/payment-reminders answered 404: the host has no PB_JOBS_SECRET configured (or runs a version without the endpoint)."
      exit 1
      ;;
    *)
      echo "::error::POST /jobs/payment-reminders answered HTTP ${status}."
      exit 1
      ;;
  esac
done
