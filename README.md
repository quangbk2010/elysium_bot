# RONS one-shot WHYPE buyer

Buys RONS with WHYPE on Elysium (chain `99901`), on the verified RONS/WHYPE
Uniswap V3-style pool. It buys either:

- **immediately**, with `--buy-now`; or
- **once**, with `--live`, when a large sell pushes the market cap below a threshold.

It can also wrap and unwrap HYPE ⇄ WHYPE.

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
```

If you omit `--amount-hype`, the script asks for the amount.

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
| `--live` | Yes | Buys X WHYPE **once**, when the [live trigger](#live-trigger---live) fires. |
| `--wrap` | Yes | Wraps the **full** amount you enter, from native HYPE into WHYPE (1:1). |
| `--unwrap-all` | Yes | Calls `withdraw()` on the wallet's **entire** WHYPE balance. |

Every mode that signs needs extra native HYPE in the wallet for gas.

### Buy now (`--buy-now`)

- It does not check market cap, sells, or the USD price feed.
- It still checks funds, allowance, gas, the deadline and the minimum output.
- You can buy again by running a new command after the previous buy is confirmed.

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

## Options

| Option | Default | Notes |
|---|---|---|
| `--rpc` | `https://rpc-live.boxa.club` | Can also be set with env `ELYSIUM_RPC`. |
| `--rpc-backup` | `https://rpc.ronspad.fun` | Can also be set with env `ELYSIUM_RPC_BACKUP`. Pass `""` to disable. |
| `--amount-hype` | *(prompt)* | An exact decimal with up to 18 places. Floats are never used. |
| `--slippage-bps` | `100` (1%) | Range 1–300. |
| `--max-gwei` | `2` | Gas-price cap. |
| `--poll` | `1` s | Minimum 0.2 s. |
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

The v1 contract was fixed at 0.5 WHYPE and cannot take a custom amount. Deploy v2 once and approve v2. This factory differs from Stockium's.

## Safety and state

- **Journal before broadcast:** every transaction is written to `rons_state/` before it is sent.
- **Pending blocks further runs:** a journal left `pending` stops later runs until you check its tx hash and nonce.
- **No automatic retries:** a reverted or uncertain transaction is never retried.
- **Never delete `rons_state/` to force a retry.** Old journals also keep the conditional-purchase history across contract versions.
- **One process per wallet:** a file lock enforces this. Different wallets or state directories are not coordinated with each other.
- Never share keys or keystore passwords.
- Downloading the script does not start anything: it runs in dry-run mode until you pass a mode flag.
