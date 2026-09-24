# Premium

Premium is a plan on this machine. It unlocks `--decide jev`. Framing, judging, and grouping
stay free, and the photo stays on disk.

## Which plan a command sees

A command reads the plan in this order:

1. `HEADSHOTS_PLAN`, when it is set. `free` and `premium` are the only names. Anything else is free, including a blank value.
2. The receipt file, when the environment variable is unset.
3. Free, when the file is missing, unreadable, or not version 1.

`HEADSHOTS_PLAN=free` wins over a premium receipt. That is how you turn premium off without deleting the file.

The receipt path is `$XDG_CONFIG_HOME/headshots/receipt.json`, or `~/.config/headshots/receipt.json` when `XDG_CONFIG_HOME` is unset. `headshots upgrade` writes that file. `headshots upgrade --receipt <path>` writes `<path>` instead, and later commands do not read `<path>` unless it is the path above.

```json
{
 "version": 1,
 "plan": "premium"
}
```

A receipt without `"version": 1` is ignored.

## Checkout

`headshots upgrade` prints a Payment Link and saves the receipt.

The link is `HEADSHOTS_CHECKOUT_URL` when that is set, otherwise the `BUY` constant in `entitlements.py`. `BUY` is empty until a real Payment Link exists. The tool does not call Stripe, and it does not read `STRIPE_SECRET_KEY`.

## What is not built yet

- A live Payment Link in `BUY`.
- Proof that anyone paid. Saving the receipt does not check a card, a webhook, or a signature. The file only records that `headshots upgrade` ran.
- A signed receipt. Plain JSON is easy to copy, so it is not a licence check.
- A Stripe secret, a Checkout Session call, or a customer object on this machine. Those stay off the client.
- `decide.remote`. The id is reserved. No backend calls it.

## What Jev receives

`--decide jev` needs premium and `TYPESAFE_API_KEY`. Each photo is one POST to `https://api.typesafe.ai/v1/systemone` with model `jev-latest`. The JSON state is the grade, the reasons, and the numeric measurements. Paths and pixels are not included. The key is sent as a bearer token and is not written to the report or the log line.

If the key is missing, the network fails, or the answer is not a probability from 0 to 1, the rest of that command uses the local pass. The tool says so once. The next command asks again.
