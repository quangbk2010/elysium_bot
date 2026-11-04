# RONS WHYPE buyer and seller

Buys RONS with WHYPE on Elysium (chain `99901`), on the verified RONS/WHYPE
Uniswap V3-style pool. It buys either:

- **immediately**, with `--buy-now`; or
- **once**, with `--live`, when a large sell pushes the market cap below a threshold.

It can also sell X% of the wallet's RONS immediately (`--sell-now`, or `--sell-loop` to stay running), and wrap and unwrap HYPE ⇄ WHYPE.

Script: [`rons_buy_3.py`](rons_buy_3.py). With no mode flag it runs as a **dry run** and never signs anything.

## Requirements

- Python ≥ 3.10

```bash
pip install "web3>=7,<8" requests
```

## Quick start

```bash
# 1. Offline checks (no RPC, keys or transactions)
python rons_buy_3.py --self-test

# 2. Encrypt your private key into a keystore (password ≥ 12 chars)
python rons_buy_3.py --init-keystore wallet.json

# 3. Deploy the buyer contract (once per wallet)
python rons_buy_3.py --deploy-router --keystore wallet.json

# 4. Wrap any shortfall and approve exactly X WHYPE to the buyer
python rons_buy_3.py --prepare --keystore wallet.json --amount-hype 0.8

# 5. Read-only market-cap check
python rons_buy_3.py --once

# 6a. Buy now ...
python rons_buy_3.py --buy-now --keystore wallet.json --amount-hype 0.8
# 6b. ... or arm the conditional buyer
python rons_buy_3.py --live --keystore wallet.json --amount-hype 0.8

# 7. Sell X% of your RONS now (deploy the seller once per wallet first)
pip install py-solc-x
python rons_buy_3.py --deploy-seller --keystore wallet.json
python rons_buy_3.py --sell-now --keystore wallet.json --sell-pct 50
# ... or stay running and sell each percent you type, with no startup delay
python rons_buy_3.py --sell-loop --keystore wallet.json
```

If you omit `--amount-hype` (or `--sell-pct`), the script asks for it.

## Modes

| Flag | Signs? | What it does |
|---|---|---|
| *(none)* | No | Dry run. Watches the pool and reports; never sends a transaction. |
| `--once` | No | Prints the current market cap once and exits. |
| `--self-test` | No | Unit checks. Uses no RPC, keys or transactions. |
| `--init-keystore FILE` | No | Encrypts a private key into a keystore file. |
| `--deploy-router` | Yes | Deploys the bundled buyer contract. Run it once per wallet. |
| `--prepare` | Yes | Wraps any WHYPE shortfall up to X, then approves exactly X to the buyer. |
| `--buy-now` | Yes | Spends X WHYPE immediately. See [Buy now](#buy-now---buy-now). |
| `--deploy-seller` | Yes | Compiles and deploys the bundled seller contract. Run it once per wallet. |
| `--sell-now` | Yes | Sells X% of the wallet's RONS immediately. See [Sell now](#sell-now---sell-now). |
| `--sell-loop` | Yes | Unlocks and verifies once, then sells each percent you type immediately. See [Sell loop](#sell-loop---sell-loop). |
| `--live` | Yes | Buys X WHYPE **once**, when the [live trigger](#live-trigger---live) fires. |
| `--wrap` | Yes | Wraps the **full** amount you enter, from native HYPE into WHYPE (1:1). |
| `--unwrap-all` | Yes | Calls `withdraw()` on the wallet's **entire** WHYPE balance. |

Every mode that signs needs extra native HYPE in the wallet for gas.

### Buy now (`--buy-now`)

- It does not check market cap, sells, or the USD price feed.
- It still checks funds, allowance, gas, the deadline (`--deadline-secs`) and the minimum output.
- You can buy again by running a new command after the previous buy is confirmed, cancelled or dropped.

### Sell now (`--sell-now`)

- Sells `--sell-pct` percent (0.01–100, up to 2 decimals; a trailing `%` is accepted) of the RONS balance **at the moment of that sell**. `100` sells everything. Two sells of `50` leave 25%, not 0%.
- **First sell only:** if the seller's RONS allowance is too low, it first sends a one-time **unlimited** `approve`, journaled like any other transaction. Every later sell is a single transaction. The seller can only pull tokens from whoever calls `sell()`, during that call, and it has no owner or sweep function. To revoke, approve 0 to the seller address in any wallet.
- Like `--buy-now`, it does not check market cap, sells, or the USD price feed. It does check gas, the deadline (`--deadline-secs`) and the minimum WHYPE output (`--slippage-bps`).
- The proceeds arrive as **WHYPE**. Run `--unwrap-all` to get native HYPE.
- After a confirmed sell it prints the WHYPE received and the RONS left.
- You can sell again by running a new command after the previous sell is confirmed, cancelled or dropped.

### Sell loop (`--sell-loop`)

- Skips the ~10 s startup on each sell: web3 import, keystore decryption (scrypt) and about 20 verification calls are done once.
- Shows your RONS balance, asks `Phan tram RONS muon ban (Enter de thoat):` and sells that percent immediately. Enter or `q` quits.
- A reverted, cancelled or dropped sell is journaled and the loop asks again. A sell whose outcome is still unknown (queued on the node) stops the loop.
- It keeps the wallet lock while it runs, so no other run can use this wallet.

### Speed

A sell is now one transaction confirmed at a 1 gwei bid. Before these changes a sell was two transactions (approve + sell) at the node's ~0.2 gwei, and each waited 26–90 s for inclusion.

- One-time unlimited approval (see above).
- `--gas-gwei` (default 1, like wallets) is the minimum gas-price bid; it never exceeds `--max-gwei`. It applies to every transaction the script sends, buys included. Cost: about 0.00015 HYPE per transaction.
- `--sell-loop` removes the startup cost.

### Wrap and unwrap

- **`--wrap`** does not buy, approve, use the buyer contract or read a price feed.
- **`--unwrap-all`** takes no amount. It reads the WHYPE balance once, so WHYPE that arrives later is not unwrapped.
- Unwrapping is **not a bridge**: the HYPE stays on Elysium and does not go to HyperEVM. It does not undo any earlier transaction.

## Live trigger (`--live`)

The buy is sent only when **both** conditions hold:

1. A **new** `Swap` in the verified pool sells RONS and pays out **≥ 9 WHYPE**.
   - This is one swap, not a sum of several.
   - Frontend and router fees are not deducted.
2. The market cap is **strictly below USD 250,000**, both right after that sell and at the final check before sending.

The market cap is computed as:

```
MC = pool price × (totalSupply − balanceOf(0x…dead)) / 1e18 × HYPE/USD
```

- **HYPE/USD** comes from CoinGecko and must be at most 120 s old.
- **Burns:** burns that reduce `totalSupply` are already counted, and the dead-address balance is deducted only once.
- **Not a full float model:** this is a burn-adjusted convention, so vesting and treasury wallets are not excluded.
- **Assumed:** 1 WHYPE = 1 HYPE.

What the trigger does and does not see:

- Watching starts at the current block, so **sells from before the start never trigger a buy**.
- After a reconnect, a missed sell still counts only if it is at most 30 s old.
- There is no mempool monitoring.
- A fill is not guaranteed, and the market cap at inclusion is not guaranteed either, because the USD check is done off-chain.
- `--live` is one-shot: once its journal (`rons_<wallet>.json`) exists, it refuses to arm again. The exception is a buy that was `replaced` or `dropped` (it never executed): that journal is archived and `--live` can be armed again.

## Options

| Option | Default | Notes |
|---|---|---|
| `--rpc` | `https://rpc-live.boxa.club` | Can also be set with env `ELYSIUM_RPC`. |
| `--rpc-backup` | `https://rpc.ronspad.fun` | Can also be set with env `ELYSIUM_RPC_BACKUP`. Pass `""` to disable. |
| `--amount-hype` | *(prompt)* | An exact decimal with up to 18 places. Floats are never used. |
| `--sell-pct` | *(prompt)* | With `--sell-now`: percent of the RONS balance, 0.01–100, up to 2 decimals. |
| `--slippage-bps` | `100` (1%) | Range 1–300. |
| `--deadline-secs` | `180` s | Swap deadline after the quote. Range 30–900. The script waits for the receipt until this deadline + 60 s. |
| `--gas-gwei` | `1` | Minimum gas-price bid. The node suggests about 0.2 gwei, but transactions at that price waited 26–90 s for inclusion. Wallets pay about 1 gwei. The bid is the higher of the two. Must be ≤ `--max-gwei`. |
| `--max-gwei` | `2` | Gas-price cap. |
| `--poll` | `10` s | Live/dry-run polling interval. Minimum 0.2 s. |
| `--max-event-age` | `30` s | Range 1–60. |
| `--max-block-age` | `600` s | Range 10–3600. |
| `--state-dir` | `./rons_state` | Location of the journals and lock files. |

**RPC failover:** the script uses the backup only if the primary is unreachable at startup. A run never switches nodes partway through, because its reorg checks and receipts depend on staying on one node.

**Status line:** in a terminal, the `block … cap USD …` status is a single line rewritten in place. Sells, trades and errors print on new lines below it. When the output is redirected to a file, the status prints one line per poll instead.

**Block age:** Elysium only produces blocks when there are transactions, so the latest block can be several minutes old. `--max-block-age` sets how old it may be.

## Buyer contract

`--deploy-router` deploys the minimal WHYPE buyer whose Solidity source is bundled in the script as `BUYER_SOURCE`. Your wallet pays the gas. The contract has:

- a fixed pool and WHYPE address;
- no owner, admin or sweep function;
- no platform fee;
- an exact WHYPE input, a deadline and a minimum output.

The script verifies the contract's runtime bytecode before every run.

**Seller contract.** `--deploy-seller` compiles `SELLER_SOURCE` (the buyer's mirror: RONS in, WHYPE out) on your machine with solc 0.8.26, using the optimizer at 200 runs and `evmVersion` paris. It needs `pip install py-solc-x`, which downloads solc the first time it runs. It has the same properties as the buyer: no owner, no sweep, no fee. After deploying, the script checks the on-chain runtime bytecode against the compiled output and saves its hash in `rons_state/seller_v1_<wallet>.json`. Every sell checks the deployed code against that hash. Only `--deploy-seller` needs py-solc-x; `--sell-now` and `--sell-loop` do not.

The v1 contract was fixed at 0.5 WHYPE and cannot take a custom amount. Deploy v2 once and approve v2. This factory differs from Stockium's.

## Safety and state

- **Journal before broadcast:** every transaction is written to `rons_state/` as `pending` before it is sent, then updated with its final status.
- **Pending journals are settled automatically.** If a send fails, the receipt wait times out, the run is interrupted, or you cancel/speed up the transaction in a wallet, the journal is checked against the chain. This happens right away when possible, and otherwise at the start of the next run (and before each sell in `--sell-loop`). You no longer need to edit or delete journals by hand.
- **Only an order still queued on the node blocks further runs**, because it may still execute. Run again later; it is re-checked each time.
- **No automatic retries:** a failed transaction is never re-sent. You start the next one yourself.
- **Never delete `rons_state/` to force a retry.** Old journals also keep the conditional-purchase history across contract versions.

### Journal statuses

| Status | Meaning | Executed? | Blocks new runs? |
|---|---|---|---|
| `pending` | Sent; outcome not known yet, or still queued on the node. | Maybe | **Yes** |
| `success` | Mined and succeeded. `block` is recorded. | Yes | No |
| `reverted` | Mined but failed, e.g. slippage or expired deadline. Gas was spent. | No | No |
| `replaced` | Its nonce was used by another transaction: a wallet **cancel** or speed-up, or a UI trade. It can never execute. | No | No |
| `dropped` | Not mined, nonce unused, and the node no longer knows it: rejected or dropped. | No | No |

`replaced` and `dropped` journals also get a `note` and a `resolved_at` time. For `dropped`, the next transaction reuses the same nonce, so even if the old one resurfaces, at most one of the two can execute.

A deploy (`--deploy-router`, `--deploy-seller`) or `--live` buy that ends up `replaced` or `dropped` is archived as `<name>_<status>_<time>.json`, so you can retry it. A `reverted` deploy still needs a manual look before retrying.
- **One process per wallet:** a file lock enforces this. Different wallets or state directories are not coordinated with each other.
- Never share keys or keystore passwords.
- Downloading the script does not start anything: it runs in dry-run mode until you pass a mode flag.
