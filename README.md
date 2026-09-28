# Everyday Rewards Auto-Boost for Home Assistant

Automatically boosts every available Woolworths Everyday Rewards offer, for as many accounts as you like.

> **Unofficial.** This integration uses the same undocumented API as the Everyday Rewards "boost" web widget. Woolworths can change or block it at any time. If that happens, Home Assistant shows a repair issue and the integration stops until it is updated.

## Install

1. In HACS, open **Integrations → ⋮ → Custom repositories** and add `https://github.com/vwylaw/ha-everyday-rewards` as an **Integration**.
2. Install **Everyday Rewards Auto-Boost** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Everyday Rewards Auto-Boost**.
4. Enter the 13-digit card number (on the card or in the app under **Card**). Optionally give the account a name.

Repeat step 3 for each account.

**Treat card numbers like passwords.** With this API, anyone who has a card number can boost offers on that account. The integration stores the number in Home Assistant's config storage and keeps it out of entity states, logs and diagnostics.

## What you get (per account)

| Entity | What it shows |
|---|---|
| `sensor.<name>_available_offers` | Offers not yet boosted; the `offers` attribute lists each offer's name (e.g. "Woolworths Beanettes 400g"), heading, points and end date |
| `sensor.<name>_boosted_offers` | Boosted offers that are still running |
| `sensor.<name>_last_boost` | When the last boost ran; attributes `boosted`, `failed`, `last_error` |
| `button.<name>_boost_all` | Boost everything now |
| `switch.<name>_auto_boost` | Turn scheduled boosting on or off |

Options (**Configure** on the integration): how often to check for new offers (1–24 hours, default 6) and whether to boost automatically (default on).

Points balance is not available: the API only returns it after a full password login.

## Service

`everyday_rewards.boost_all` boosts every available offer. Pass `device_id` to limit it to particular accounts; with no target it boosts all accounts.

## Event and automation example

After each boost the integration fires `everyday_rewards_boosted` with `entry_id`, `account`, `boosted`, `failed` and `offers` (the names of the offers boosted).

```yaml
automation:
  - alias: Tell me what got boosted
    triggers:
      - trigger: event
        event_type: everyday_rewards_boosted
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.boosted > 0 }}"
    actions:
      - action: notify.notify
        data:
          message: >
            Boosted {{ trigger.event.data.boosted }} offers for
            {{ trigger.event.data.account }}:
            {{ trigger.event.data.offers | join(', ') }}
```

## Development

```bash
/opt/homebrew/bin/python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```
