#!/usr/bin/env python3
"""RONS conditional, one-shot WHYPE buyer. Python >=3.10.
Install: pip install "web3>=7,<8" requests

1. python rons_buy.py --self-test
2. python rons_buy.py --init-keystore wallet.json
3. python rons_buy.py --deploy-router --keystore wallet.json
4. python rons_buy.py --prepare --keystore wallet.json
5. python rons_buy.py --once             # read-only current MC
6. python rons_buy.py --live --keystore wallet.json

Buys 0.5 WHYPE ONCE only when BOTH hold:
- A NEW Swap in the verified RONS/WHYPE pool sells RONS and the pool outputs
  >=9 WHYPE (one Swap, not sums, before frontend fees).
- MC after that sell AND at final preflight is strictly below USD 250,000.
MC = pool price * (totalSupply - balanceOf(dead)) / 1e18 * CoinGecko HYPE/USD.
Real burns lowering totalSupply are already counted; dead balance is deducted
only once. This is the project's burn-adjusted convention, not proof of all
vesting/treasury exclusions. WHYPE/HYPE parity is assumed.

Start cursor is current head: OLD sells never trigger. Reconnect backlog is
accepted only while events are <=30 seconds old. No mempool monitoring.
A pool Swap output is used; frontend/router fees are not deducted from the 9.
Default: 1-second polling, 1% slippage, fresh HYPE/USD <=120 seconds.
No guarantee of instant fill or USD market cap at inclusion (USD check is offchain).

This factory differs from Stockium. --deploy-router deploys the included minimal
WHYPE buyer once, with gas paid by your wallet. It has fixed pool/WHYPE, no owner,
no admin/sweep, no platform fee, exact 0.5 WHYPE input, deadline and minOut.
Source is included below; runtime bytecode is verified before each run.
--prepare wraps any shortfall to 0.5 WHYPE and approves only 0.5 to this buyer.
--live unlocks your local keystore once and automatically signs on the trigger.
Keep native HYPE for deployment/preparation/gas. Never share keys/passwords.
Never delete rons_state to retry an uncertain/pending transaction; inspect its
journal hash and nonce. Use one bot/wallet; other wallets/state directories are
not coordinated. Reverted/uncertain swaps are never automatically retried.
Default mode is dry-run; no daemon/automation is started by downloading this file.
"""
import argparse
import contextlib
from decimal import Decimal, getcontext
import getpass
import json
import os
from pathlib import Path
import sys
import time

getcontext().prec = 70
D = Decimal
CHAIN = 99901
AMOUNT = 500_000_000_000_000_000
THRESHOLD = D('250000')
DEAD = '0x000000000000000000000000000000000000dead'
MIN_SELL = 9 * 10**18
TOKEN = '0x44d13223e2024c6f3f957d5c9ab98f8a550061f3'
WHYPE = '0xba876237b0f021a6c6d852d6c26e107997cc5e81'
# Router address is loaded from your successful --deploy-router receipt.
POOL = '0xa61b8d703a54bd119bcb7904aa68c9a40363cb7f'
FACTORY = '0x24e21e3f2b0bb0c166ec3eaff1e615ab14cdd85f'
BUYER_ABI = [{'inputs': [], 'name': 'AMOUNT', 'outputs': [{'internalType': 'uint256', 'name': '', 'type': 'uint256'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [], 'name': 'POOL', 'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [], 'name': 'WHYPE', 'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [{'internalType': 'uint256', 'name': 'minimumOut', 'type': 'uint256'}, {'internalType': 'uint256', 'name': 'deadline', 'type': 'uint256'}], 'name': 'buy', 'outputs': [{'internalType': 'uint256', 'name': 'output', 'type': 'uint256'}], 'stateMutability': 'nonpayable', 'type': 'function'}, {'inputs': [{'internalType': 'int256', 'name': 'd0', 'type': 'int256'}, {'internalType': 'int256', 'name': 'd1', 'type': 'int256'}, {'internalType': 'bytes', 'name': '', 'type': 'bytes'}], 'name': 'uniswapV3SwapCallback', 'outputs': [], 'stateMutability': 'nonpayable', 'type': 'function'}]
BUYER_BYTECODE = '0x6080604052348015600f57600080fd5b506106428061001f6000396000f3fe608060405234801561001057600080fd5b50600436106100575760003560e01c806359f613a41461005c5780637535d24614610094578063d1789176146100af578063d6febde8146100cc578063fa461e33146100df575b600080fd5b61007773ba876237b0f021a6c6d852d6c26e107997cc5e8181565b6040516001600160a01b0390911681526020015b60405180910390f35b61007773a61b8d703a54bd119bcb7904aa68c9a40363cb7f81565b6100be6706f05b59d3b2000081565b60405190815260200161008b565b6100be6100da3660046104cf565b6100f4565b6100f26100ed3660046104f1565b610308565b005b6000814211156101355760405162461bcd60e51b8152602060048201526007602482015266195e1c1a5c995960ca1b60448201526064015b60405180910390fd5b6000546001600160a01b03161561017a5760405162461bcd60e51b81526020600482015260096024820152681c99595b9d1c985b9d60ba1b604482015260640161012c565b600080546001600160a01b0319163390811782556706f05b59d3b200006001819055604051630251596160e31b8152600481019290925260248201839052604482015273fffd8963efd1fc6a506488495d951d5263988d25606482015260a0608482015260a48101829052819073a61b8d703a54bd119bcb7904aa68c9a40363cb7f9063128acb089060c40160408051808303816000875af1158015610224573d6000803e3d6000fd5b505050506040513d601f19601f820116820180604052508101906102489190610574565b9150915060008212801561026357506706f05b59d3b2000081145b801561026f5750600154155b6102aa5760405162461bcd60e51b815260206004820152600c60248201526b1c185c9d1a585b08199a5b1b60a21b604482015260640161012c565b6102b3826105ae565b9250848310156102f05760405162461bcd60e51b8152602060048201526008602482015267736c69707061676560c01b604482015260640161012c565b5050600080546001600160a01b031916905592915050565b3373a61b8d703a54bd119bcb7904aa68c9a40363cb7f14801561033557506000546001600160a01b031615155b6103795760405162461bcd60e51b8152602060048201526015602482015274756e617574686f72697a65642063616c6c6261636b60581b604482015260640161012c565b6000841280156103895750600083135b801561039757506001548311155b6103d25760405162461bcd60e51b815260206004820152600c60248201526b1a5b9d985b1a59081919589d60a21b604482015260640161012c565b82600160008282546103e491906105ca565b90915550506000546040516323b872dd60e01b81526001600160a01b03909116600482015273a61b8d703a54bd119bcb7904aa68c9a40363cb7f60248201526044810184905273ba876237b0f021a6c6d852d6c26e107997cc5e81906323b872dd906064016020604051808303816000875af1158015610468573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061048c91906105e3565b6104c95760405162461bcd60e51b815260206004820152600e60248201526d1c185e5b595b9d0819985a5b195960921b604482015260640161012c565b50505050565b600080604083850312156104e257600080fd5b50508035926020909101359150565b6000806000806060858703121561050757600080fd5b8435935060208501359250604085013567ffffffffffffffff81111561052c57600080fd5b8501601f8101871361053d57600080fd5b803567ffffffffffffffff81111561055457600080fd5b87602082840101111561056657600080fd5b949793965060200194505050565b6000806040838503121561058757600080fd5b505080516020909101519092909150565b634e487b7160e01b600052601160045260246000fd5b6000600160ff1b82016105c3576105c3610598565b5060000390565b818103818111156105dd576105dd610598565b92915050565b6000602082840312156105f557600080fd5b8151801515811461060557600080fd5b939250505056fea26469706673582212200ec523f39ee5051e2e103904df4616cb2d711cd100bb4a17e7f89d7d6618ad0964736f6c634300081a0033'
BUYER_RUNTIME = '0x608060405234801561001057600080fd5b50600436106100575760003560e01c806359f613a41461005c5780637535d24614610094578063d1789176146100af578063d6febde8146100cc578063fa461e33146100df575b600080fd5b61007773ba876237b0f021a6c6d852d6c26e107997cc5e8181565b6040516001600160a01b0390911681526020015b60405180910390f35b61007773a61b8d703a54bd119bcb7904aa68c9a40363cb7f81565b6100be6706f05b59d3b2000081565b60405190815260200161008b565b6100be6100da3660046104cf565b6100f4565b6100f26100ed3660046104f1565b610308565b005b6000814211156101355760405162461bcd60e51b8152602060048201526007602482015266195e1c1a5c995960ca1b60448201526064015b60405180910390fd5b6000546001600160a01b03161561017a5760405162461bcd60e51b81526020600482015260096024820152681c99595b9d1c985b9d60ba1b604482015260640161012c565b600080546001600160a01b0319163390811782556706f05b59d3b200006001819055604051630251596160e31b8152600481019290925260248201839052604482015273fffd8963efd1fc6a506488495d951d5263988d25606482015260a0608482015260a48101829052819073a61b8d703a54bd119bcb7904aa68c9a40363cb7f9063128acb089060c40160408051808303816000875af1158015610224573d6000803e3d6000fd5b505050506040513d601f19601f820116820180604052508101906102489190610574565b9150915060008212801561026357506706f05b59d3b2000081145b801561026f5750600154155b6102aa5760405162461bcd60e51b815260206004820152600c60248201526b1c185c9d1a585b08199a5b1b60a21b604482015260640161012c565b6102b3826105ae565b9250848310156102f05760405162461bcd60e51b8152602060048201526008602482015267736c69707061676560c01b604482015260640161012c565b5050600080546001600160a01b031916905592915050565b3373a61b8d703a54bd119bcb7904aa68c9a40363cb7f14801561033557506000546001600160a01b031615155b6103795760405162461bcd60e51b8152602060048201526015602482015274756e617574686f72697a65642063616c6c6261636b60581b604482015260640161012c565b6000841280156103895750600083135b801561039757506001548311155b6103d25760405162461bcd60e51b815260206004820152600c60248201526b1a5b9d985b1a59081919589d60a21b604482015260640161012c565b82600160008282546103e491906105ca565b90915550506000546040516323b872dd60e01b81526001600160a01b03909116600482015273a61b8d703a54bd119bcb7904aa68c9a40363cb7f60248201526044810184905273ba876237b0f021a6c6d852d6c26e107997cc5e81906323b872dd906064016020604051808303816000875af1158015610468573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061048c91906105e3565b6104c95760405162461bcd60e51b815260206004820152600e60248201526d1c185e5b595b9d0819985a5b195960921b604482015260640161012c565b50505050565b600080604083850312156104e257600080fd5b50508035926020909101359150565b6000806000806060858703121561050757600080fd5b8435935060208501359250604085013567ffffffffffffffff81111561052c57600080fd5b8501601f8101871361053d57600080fd5b803567ffffffffffffffff81111561055457600080fd5b87602082840101111561056657600080fd5b949793965060200194505050565b6000806040838503121561058757600080fd5b505080516020909101519092909150565b634e487b7160e01b600052601160045260246000fd5b6000600160ff1b82016105c3576105c3610598565b5060000390565b818103818111156105dd576105dd610598565b92915050565b6000602082840312156105f557600080fd5b8151801515811461060557600080fd5b939250505056fea26469706673582212200ec523f39ee5051e2e103904df4616cb2d711cd100bb4a17e7f89d7d6618ad0964736f6c634300081a0033'
BUYER_SOURCE = '// SPDX-License-Identifier: MIT\npragma solidity 0.8.26;\ninterface IERC20 { function transferFrom(address,address,uint256) external returns(bool); }\ninterface IPool { function swap(address,bool,int256,uint160,bytes calldata) external returns(int256,int256); }\ncontract RonsWhypeBuyer {\n    address public constant WHYPE = 0xbA876237B0F021A6c6D852d6c26E107997cC5E81;\n    address public constant POOL = 0xa61b8d703A54bD119bCB7904aA68C9a40363cb7F;\n    uint256 public constant AMOUNT = 0.5 ether;\n    address private payer;\n    uint256 private remaining;\n    function buy(uint256 minimumOut, uint256 deadline) external returns(uint256 output) {\n        require(block.timestamp <= deadline, "expired");\n        require(payer == address(0), "reentrant");\n        payer = msg.sender;\n        remaining = AMOUNT;\n        (int256 d0, int256 d1) = IPool(POOL).swap(msg.sender, false, int256(AMOUNT),\n            1461446703485210103287273052203988822378723970341, "");\n        require(d0 < 0 && d1 == int256(AMOUNT) && remaining == 0, "partial fill");\n        output = uint256(-d0);\n        require(output >= minimumOut, "slippage");\n        payer = address(0);\n    }\n    function uniswapV3SwapCallback(int256 d0, int256 d1, bytes calldata) external {\n        require(msg.sender == POOL && payer != address(0), "unauthorized callback");\n        require(d0 < 0 && d1 > 0 && uint256(d1) <= remaining, "invalid debt");\n        remaining -= uint256(d1);\n        require(IERC20(WHYPE).transferFrom(payer, POOL, uint256(d1)), "payment failed");\n    }\n}\n'
FEE = 10000

def fn(name, ins, outs, mut='view'):
    return dict(type='function', name=name, stateMutability=mut,
                inputs=[dict(name='p'+str(i), type=t) for i,t in enumerate(ins)],
                outputs=[dict(type=t) for t in outs])

ERC = [fn('balanceOf',['address'],['uint256']), fn('totalSupply',[],['uint256']),
       fn('allowance',['address','address'],['uint256']),
       fn('approve',['address','uint256'],['bool'],'nonpayable'),
       fn('deposit',[],[],'payable')]
PAIR = [fn('token0',[],['address']), fn('token1',[],['address']),
        fn('fee',[],['uint24']), fn('factory',[],['address']),
        fn('slot0',[],['uint160','int24','uint16','uint16','uint16','uint8','bool'])]
PAIR.append(dict(type='event',name='Swap',anonymous=False,inputs=[
    dict(name='sender',type='address',indexed=True),dict(name='recipient',type='address',indexed=True),
    *[dict(name=n,type=t,indexed=False) for n,t in [('amount0','int256'),('amount1','int256'),
    ('sqrtPriceX96','uint160'),('liquidity','uint128'),('tick','int24')]]]))

FAC = [fn('getPool',['address','address','uint24'],['address'])]
def tuple_fn(name, fields, outs):
    x=fn(name,[],outs,'nonpayable')
    x['inputs']=[dict(name='p',type='tuple',components=[dict(name=n,type=t) for n,t in fields])]
    return x
def cap_from_sqrt(sqrt, usd, supply_wei, dead_wei):
    if sqrt <= 0 or usd <= 0: raise ValueError('Invalid price')
    if supply_wei < dead_wei or dead_wei < 0: raise ValueError('Invalid supply')
    return (D(sqrt)/D(2**96))**2 * usd * D(supply_wei-dead_wei)/D(10**18)

def min_output(quote, bps):
    if quote <= 0 or not 1 <= bps <= 300: raise ValueError('Invalid quote/slippage')
    return quote*(10000-bps)//10000

def fresh(timestamp, max_age):
    age=time.time()-timestamp
    if not -10 <= age <= max_age: raise ValueError('Stale/future price or block timestamp')

def write_json(path, data, exclusive=False):
    if exclusive:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump(data,f);f.flush();os.fsync(f.fileno())
    else:
        tmp=path.with_suffix(path.suffix+'.tmp')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump(data,f);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)

@contextlib.contextmanager
def process_lock(path):
    # OS lock is released after a crash; the journal survives and prevents rebuy.
    f=open(str(path)+'.lock','a+b');f.seek(0);f.write(b'0');f.flush();f.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        f.close();raise RuntimeError('Another process is using this wallet/journal')
    try: yield
    finally: f.close()

class PriceFeed:
    def __init__(self): self.value=None;self.updated=0;self.fetched=0
    def get(self):
        import requests
        if self.value is None or time.monotonic()-self.fetched>=30:
            headers={}
            if os.getenv('COINGECKO_DEMO_API_KEY'):
                headers['x-cg-demo-api-key']=os.environ['COINGECKO_DEMO_API_KEY']
            response=requests.get('https://api.coingecko.com/api/v3/simple/price',
                params=dict(ids='hyperliquid',vs_currencies='usd',
                            include_last_updated_at='true'),headers=headers,timeout=8)
            response.raise_for_status();r=response.json()['hyperliquid']
            value=D(str(r['usd']));updated=int(r['last_updated_at'])
            fresh(updated,120)
            if not value.is_finite() or value<=0: raise ValueError('Bad HYPE/USD')
            self.value=value;self.updated=updated;self.fetched=time.monotonic()
        fresh(self.updated,120)
        return self.value

class Buyer:
    def __init__(self,a,account):
        from web3 import Web3
        self.a=a;self.account=account
        self.w=Web3(Web3.HTTPProvider(a.rpc,request_kwargs={'timeout':8}))
        if self.w.eth.chain_id!=CHAIN: raise RuntimeError('Wrong chain: require Elysium 99901')
        self.addr=account.address if account else None
        def contract(address,abi):
            address=Web3.to_checksum_address(address)
            if not self.w.eth.get_code(address): raise RuntimeError('No contract at '+address)
            return self.w.eth.contract(address=address,abi=abi)
        self.token=contract(TOKEN,ERC);self.wh=contract(WHYPE,ERC)
        self.pool=contract(POOL,PAIR);self.factory=contract(FACTORY,FAC)
        self.router=None
        self.deployment_path=a.state_dir/('buyer_'+self.addr.lower()+'.json') if self.addr else None
        if self.addr and self.deployment_path.exists():
            address=json.loads(self.deployment_path.read_text())['address']
            self.router=contract(address,BUYER_ABI)
            if bytes(self.w.eth.get_code(self.router.address)) != bytes.fromhex(BUYER_RUNTIME[2:]):
                raise RuntimeError('Buyer runtime mismatch; refusing approval/trade')
        if self.addr and not self.router and not a.deploy_router:
            raise RuntimeError('Run --deploy-router first')
        if (self.pool.functions.token0().call().lower()!=TOKEN or
            self.pool.functions.token1().call().lower()!=WHYPE or
            self.pool.functions.fee().call()!=FEE or
            self.pool.functions.factory().call().lower()!=FACTORY or
            self.factory.functions.getPool(self.token.address,self.wh.address,FEE).call().lower()!=POOL):
            raise RuntimeError('Pool identity/fee mismatch')
        self.feed=PriceFeed()

    def observe(self, block=None, sqrt=None):
        usd=self.feed.get();h=self.w.eth.get_block('latest' if block is None else block)
        fresh(h['timestamp'],60)
        if sqrt is None: sqrt=self.pool.functions.slot0().call(block_identifier=h['number'])[0]
        supply=self.token.functions.totalSupply().call(block_identifier=h['number'])
        dead=self.token.functions.balanceOf(self.w.to_checksum_address(DEAD)).call(block_identifier=h['number'])
        return cap_from_sqrt(sqrt,usd,supply,dead),usd,h

    def deploy_router(self):
        if self.router: print('Already deployed and verified:',self.router.address);return
        constructor=self.w.eth.contract(abi=BUYER_ABI,bytecode=BUYER_BYTECODE).constructor()
        journal=self.a.state_dir/('deploy_'+self.addr.lower()+'.json')
        if journal.exists(): raise RuntimeError('Deployment attempt exists: inspect journal before retrying')
        rec=self.submit(self.tx(constructor),journal)
        address=rec.contractAddress
        if bytes(self.w.eth.get_code(address))!=bytes.fromhex(BUYER_RUNTIME[2:]):
            raise RuntimeError('Deployed runtime mismatch')
        write_json(self.deployment_path,dict(address=address,chain=CHAIN,pool=POOL),exclusive=True)
        print('Buyer deployed:',address,'Run --prepare next.')

    def ready(self):
        if self.wh.functions.balanceOf(self.addr).call()<AMOUNT:
            raise RuntimeError('Need 0.5 WHYPE first: run --prepare')
        if self.wh.functions.allowance(self.addr,self.router.address).call()<AMOUNT:
            raise RuntimeError('Need router allowance first: run --prepare')

    def tx(self,function,value=0):
        gas_price=self.w.eth.gas_price
        if gas_price>int(D(str(self.a.max_gwei))*D(10**9)):
            raise RuntimeError('Gas price above configured cap')
        base={'from':self.addr,'value':value}
        gas=int(function.estimate_gas(base)*1.25)+10000
        if gas>2_000_000: raise RuntimeError('Gas estimate exceeds 2,000,000')
        if self.w.eth.get_balance(self.addr)<value+gas*gas_price:
            raise RuntimeError('Insufficient native HYPE for value and gas')
        return function.build_transaction(dict(base,chainId=CHAIN,
            nonce=self.w.eth.get_transaction_count(self.addr,'pending'),
            gas=gas,gasPrice=gas_price))

    def submit(self,tx,journal=None):
        signed=self.account.sign_transaction(tx)
        h=self.w.keccak(signed.raw_transaction).hex()
        if not h.startswith('0x'): h='0x'+h
        if journal:
            # Persist BEFORE broadcast. Any uncertainty means stop, never buy again.
            write_json(journal,dict(status='pending',tx_hash=h,nonce=tx['nonce'],
                       wallet=self.addr,chain_id=CHAIN,token=TOKEN,
                       amount_whype_wei=AMOUNT,created_at=time.time()),exclusive=True)
        print('Broadcast:',h,flush=True)
        self.w.eth.send_raw_transaction(signed.raw_transaction)
        rec=self.w.eth.wait_for_transaction_receipt(h,timeout=120,poll_latency=1)
        if journal:
            data=json.loads(journal.read_text());data.update(status='success' if rec.status==1 else 'reverted',block=rec.blockNumber,
                contract_address=rec.contractAddress)
            write_json(journal,data)
        if rec.status!=1: raise RuntimeError('Transaction reverted; journal prevents automatic retry')
        print('Confirmed in block',rec.blockNumber,flush=True)
        return rec

    def prepare(self):
        have=self.wh.functions.balanceOf(self.addr).call()
        if have<AMOUNT:
            deficit=AMOUNT-have
            print('Wrapping HYPE:',D(deficit)/D(10**18),flush=True)
            self.submit(self.tx(self.wh.functions.deposit(),deficit),
                        self.a.state_dir/('wrap_'+self.addr.lower()+'.json'))
        if self.wh.functions.allowance(self.addr,self.router.address).call()<AMOUNT:
            self.submit(self.tx(self.wh.functions.approve(self.router.address,AMOUNT)),
                        self.a.state_dir/('approve_'+self.addr.lower()+'.json'))
        self.ready();print('Ready: 0.5 WHYPE and allowance. Run --live to arm.')

    def event_valid(self,event):
        fresh(event['timestamp'],self.a.max_event_age)
        h=self.w.eth.get_block(event['block'])
        if h['hash'].hex()!=event['hash']: raise RuntimeError('Sell block reorged')
        cap,_,_=self.observe(event['block'],event['sqrt'])
        return event['sell_wei']>=MIN_SELL and cap<THRESHOLD

    def buy(self,journal,event):
        self.ready()
        if not self.event_valid(event): return False
        cap,_,h=self.observe()
        if cap>=THRESHOLD: return False
        deadline=int(h['timestamp'])+30
        # eth_call executes the real callback/payment in a discarded state, not a transaction.
        quote=self.router.functions.buy(0,deadline).call({'from':self.addr})
        minimum=min_output(quote,self.a.slippage_bps)
        swap=self.router.functions.buy(minimum,deadline)
        swap.call({'from':self.addr})
        tx=self.tx(swap)
        cap,usd,latest=self.observe()
        if cap>=THRESHOLD or not self.event_valid(event): return False
        if latest['timestamp']>=deadline: return False
        print('TRIGGER sell',D(event['sell_wei'])/D(10**18),'WHYPE',event['tx'],
              'cap USD',round(cap,2),'minimum tokens',D(minimum)/D(10**18),flush=True)
        self.submit(tx,journal);return True

def sell_amount(args):
    # Verified pool order: token0=RONS, token1=WHYPE.
    return -int(args['amount1']) if int(args['amount0'])>0 and int(args['amount1'])<0 else 0

def self_test():
    import tempfile
    # Threshold is strictly less; minOut is integer-rounded down; stale prices fail closed.
    assert not D('250000')<THRESHOLD
    assert D('249999.99')<THRESHOLD
    assert cap_from_sqrt(2**96,D('1'),10**27,250_000_000*10**18)==D('750000000')
    assert cap_from_sqrt(2**96,D('1'),750*10**18,0)==D('750')
    assert sell_amount({'amount0':1,'amount1':-9*10**18})==MIN_SELL
    assert sell_amount({'amount0':1,'amount1':-(9*10**18-1)})<MIN_SELL
    assert sell_amount({'amount0':-1,'amount1':9*10**18})==0
    assert not any(sell_amount({'amount0':1,'amount1':-5*10**18})>=MIN_SELL for _ in range(2))
    assert min_output(10001,100)==9900
    try: fresh(time.time()-121,120)
    except ValueError: pass
    else: raise AssertionError('Stale data accepted')
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)/'journal.json';write_json(p,{'status':'pending'},exclusive=True)
        try: write_json(p,{'status':'pending'},exclusive=True)
        except FileExistsError: pass
        else: raise AssertionError('Duplicate attempt allowed')
        write_json(p,{'status':'success'});assert json.loads(p.read_text())['status']=='success'
    print('Self-tests passed (no RPC, keys or transactions).')

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--live',action='store_true');modes.add_argument('--prepare',action='store_true')
    modes.add_argument('--deploy-router',action='store_true')
    modes.add_argument('--init-keystore',type=Path);modes.add_argument('--self-test',action='store_true')
    p.add_argument('--keystore',type=Path);p.add_argument('--once',action='store_true')
    p.add_argument('--rpc',default=os.getenv('ELYSIUM_RPC','https://rpc-live.boxa.club'))
    p.add_argument('--max-event-age',type=int,default=30)
    p.add_argument('--poll',type=float,default=1);p.add_argument('--slippage-bps',type=int,default=100)
    p.add_argument('--max-gwei',type=D,default=D('2'));p.add_argument('--state-dir',type=Path,default=Path(__file__).resolve().parent/'rons_state')
    a=p.parse_args()
    if a.self_test: self_test();return
    if not 1<=a.max_event_age<=60 or a.poll<0.2 or not 1<=a.slippage_bps<=300 or a.max_gwei<=0: p.error('Invalid poll/slippage/gas settings')
    from eth_account import Account
    if a.init_keystore:
        key=getpass.getpass('Private key (local input, hidden): ')
        account=Account.from_key(key);password=getpass.getpass('New keystore password: ')
        if len(password)<12 or password!=getpass.getpass('Repeat password: '):
            raise RuntimeError('Passwords must match and have at least 12 characters')
        write_json(a.init_keystore,Account.encrypt(account.key,password),exclusive=True)
        print('Encrypted keystore created for',account.address);return
    account=None
    if a.live or a.prepare or a.deploy_router:
        if not a.keystore: p.error('--keystore is required for live/prepare/deploy')
        key=Account.decrypt(json.loads(a.keystore.read_text()),getpass.getpass('Keystore password: '))
        account=Account.from_key(key);del key
    a.state_dir.mkdir(parents=True,exist_ok=True)
    journal=a.state_dir/('rons_'+account.address.lower()+'.json' if account else 'dryrun.json')
    with process_lock(journal):
        if account and journal.exists():
            print('Existing swap attempt; refusing another buy:',journal.read_text());return
        buyer=Buyer(a,account)
        if a.deploy_router: buyer.deploy_router();return
        if a.prepare: buyer.prepare();return
        if a.live: buyer.ready()
        print('LIVE ARMED' if a.live else 'DRY RUN: no transactions',flush=True)
        errors=0
        cursor=buyer.w.eth.get_block('latest')
        print('Watching NEW sells after block',cursor['number'],flush=True)
        while True:
            try:
                cap,usd,h=buyer.observe()
                print('block',h['number'],'cap USD',round(cap,2),'HYPE/USD',usd,flush=True)
                if a.once: return
                if h['number']<cursor['number'] or buyer.w.eth.get_block(cursor['number'])['hash']!=cursor['hash']:
                    raise SystemExit('Head regressed/reorged: stopped; restart to watch new events')
                end=min(h['number'],cursor['number']+1000)
                logs=buyer.pool.events.Swap().get_logs(from_block=cursor['number']+1,to_block=end) if end>cursor['number'] else []
                for log in logs:
                    if log.get('removed',False): continue
                    amount=sell_amount(log['args'])
                    if amount<MIN_SELL: continue
                    bh=buyer.w.eth.get_block(log['blockNumber'])
                    event=dict(block=log['blockNumber'],hash=log['blockHash'].hex(),
                               timestamp=bh['timestamp'],sell_wei=amount,
                               sqrt=int(log['args']['sqrtPriceX96']),tx=log['transactionHash'].hex())
                    if time.time()-event['timestamp']>a.max_event_age: continue
                    postcap,_,_=buyer.observe(event['block'],event['sqrt'])
                    print('New qualifying-size sell:',D(amount)/D(10**18),'WHYPE; post-sell cap',round(postcap,2),flush=True)
                    if postcap>=THRESHOLD or cap>=THRESHOLD: continue
                    if not a.live: print('Would buy 0.5 WHYPE; dry-run stops.');return
                    if buyer.buy(journal,event): return
                cursor=buyer.w.eth.get_block(end)
                errors=0
            except Exception as e:
                # No exception logs containing signed payloads, keys or credential-bearing URLs.
                if journal.exists():
                    print('Stopped after swap attempt. Inspect journal:',journal);raise RuntimeError('Broadcast/receipt uncertain; manual verification required') from None
                errors+=1;print('Read/preflight unavailable; no order sent. Error:',type(e).__name__,flush=True)
                if a.once: raise RuntimeError('Read-only check failed; no order sent') from None
                if errors>=10: raise RuntimeError('10 consecutive failures; stopped') from None
            if a.once: return
            time.sleep(a.poll)

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: print('Stopped by user. Pending transactions, if any, are not cancelled.')
    except Exception as e: print('STOP:',str(e),file=sys.stderr);sys.exit(1)
