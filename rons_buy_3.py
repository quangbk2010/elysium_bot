#!/usr/bin/env python3
"""RONS one-shot WHYPE buyer for Elysium (chain 99901). Dry-run by default.
See README.md for setup, modes, the live trigger and safety notes.
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
THRESHOLD = D('250000')
DEAD = '0x000000000000000000000000000000000000dead'
MIN_SELL = 9 * 10**18
TOKEN = '0x44d13223e2024c6f3f957d5c9ab98f8a550061f3'
WHYPE = '0xba876237b0f021a6c6d852d6c26e107997cc5e81'
# Router address is loaded from your successful --deploy-router receipt.
POOL = '0xa61b8d703a54bd119bcb7904aa68c9a40363cb7f'
FACTORY = '0x24e21e3f2b0bb0c166ec3eaff1e615ab14cdd85f'
BUYER_ABI = [{'inputs': [], 'name': 'POOL', 'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [], 'name': 'WHYPE', 'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [{'internalType': 'uint256', 'name': 'amountIn', 'type': 'uint256'}, {'internalType': 'uint256', 'name': 'minimumOut', 'type': 'uint256'}, {'internalType': 'uint256', 'name': 'deadline', 'type': 'uint256'}], 'name': 'buy', 'outputs': [{'internalType': 'uint256', 'name': 'output', 'type': 'uint256'}], 'stateMutability': 'nonpayable', 'type': 'function'}, {'inputs': [{'internalType': 'int256', 'name': 'd0', 'type': 'int256'}, {'internalType': 'int256', 'name': 'd1', 'type': 'int256'}, {'internalType': 'bytes', 'name': '', 'type': 'bytes'}], 'name': 'uniswapV3SwapCallback', 'outputs': [], 'stateMutability': 'nonpayable', 'type': 'function'}]
BUYER_BYTECODE = '0x6080604052348015600f57600080fd5b506106788061001f6000396000f3fe608060405234801561001057600080fd5b506004361061004c5760003560e01c806340993b261461005157806359f613a4146100775780637535d246146100aa578063fa461e33146100c5575b600080fd5b61006461005f3660046104fb565b6100da565b6040519081526020015b60405180910390f35b61009273ba876237b0f021a6c6d852d6c26e107997cc5e8181565b6040516001600160a01b03909116815260200161006e565b61009273a61b8d703a54bd119bcb7904aa68c9a40363cb7f81565b6100d86100d3366004610527565b610334565b005b60008142111561011b5760405162461bcd60e51b8152602060048201526007602482015266195e1c1a5c995960ca1b60448201526064015b60405180910390fd5b6000546001600160a01b0316156101605760405162461bcd60e51b81526020600482015260096024820152681c99595b9d1c985b9d60ba1b6044820152606401610112565b60008411801561017757506001600160ff1b038411155b6101b45760405162461bcd60e51b815260206004820152600e60248201526d1a5b9d985b1a5908185b5bdd5b9d60921b6044820152606401610112565b600080546001600160a01b0319163390811782556001869055604051630251596160e31b81526004810191909152602481018290526044810186905273fffd8963efd1fc6a506488495d951d5263988d25606482015260a0608482015260a48101829052819073a61b8d703a54bd119bcb7904aa68c9a40363cb7f9063128acb089060c40160408051808303816000875af1158015610257573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061027b91906105aa565b9150915060008212801561028e57508581145b801561029a5750600154155b6102d55760405162461bcd60e51b815260206004820152600c60248201526b1c185c9d1a585b08199a5b1b60a21b6044820152606401610112565b6102de826105e4565b92508483101561031b5760405162461bcd60e51b8152602060048201526008602482015267736c69707061676560c01b6044820152606401610112565b5050600080546001600160a01b03191690559392505050565b3373a61b8d703a54bd119bcb7904aa68c9a40363cb7f14801561036157506000546001600160a01b031615155b6103a55760405162461bcd60e51b8152602060048201526015602482015274756e617574686f72697a65642063616c6c6261636b60581b6044820152606401610112565b6000841280156103b55750600083135b80156103c357506001548311155b6103fe5760405162461bcd60e51b815260206004820152600c60248201526b1a5b9d985b1a59081919589d60a21b6044820152606401610112565b82600160008282546104109190610600565b90915550506000546040516323b872dd60e01b81526001600160a01b03909116600482015273a61b8d703a54bd119bcb7904aa68c9a40363cb7f60248201526044810184905273ba876237b0f021a6c6d852d6c26e107997cc5e81906323b872dd906064016020604051808303816000875af1158015610494573d6000803e3d6000fd5b505050506040513d601f19601f820116820180604052508101906104b89190610619565b6104f55760405162461bcd60e51b815260206004820152600e60248201526d1c185e5b595b9d0819985a5b195960921b6044820152606401610112565b50505050565b60008060006060848603121561051057600080fd5b505081359360208301359350604090920135919050565b6000806000806060858703121561053d57600080fd5b8435935060208501359250604085013567ffffffffffffffff81111561056257600080fd5b8501601f8101871361057357600080fd5b803567ffffffffffffffff81111561058a57600080fd5b87602082840101111561059c57600080fd5b949793965060200194505050565b600080604083850312156105bd57600080fd5b505080516020909101519092909150565b634e487b7160e01b600052601160045260246000fd5b6000600160ff1b82016105f9576105f96105ce565b5060000390565b81810381811115610613576106136105ce565b92915050565b60006020828403121561062b57600080fd5b8151801515811461063b57600080fd5b939250505056fea26469706673582212204b891a015d581c15543a1b069be5a0720c81e0b34ca54a47757d53628c6d347264736f6c634300081a0033'
BUYER_RUNTIME = '0x608060405234801561001057600080fd5b506004361061004c5760003560e01c806340993b261461005157806359f613a4146100775780637535d246146100aa578063fa461e33146100c5575b600080fd5b61006461005f3660046104fb565b6100da565b6040519081526020015b60405180910390f35b61009273ba876237b0f021a6c6d852d6c26e107997cc5e8181565b6040516001600160a01b03909116815260200161006e565b61009273a61b8d703a54bd119bcb7904aa68c9a40363cb7f81565b6100d86100d3366004610527565b610334565b005b60008142111561011b5760405162461bcd60e51b8152602060048201526007602482015266195e1c1a5c995960ca1b60448201526064015b60405180910390fd5b6000546001600160a01b0316156101605760405162461bcd60e51b81526020600482015260096024820152681c99595b9d1c985b9d60ba1b6044820152606401610112565b60008411801561017757506001600160ff1b038411155b6101b45760405162461bcd60e51b815260206004820152600e60248201526d1a5b9d985b1a5908185b5bdd5b9d60921b6044820152606401610112565b600080546001600160a01b0319163390811782556001869055604051630251596160e31b81526004810191909152602481018290526044810186905273fffd8963efd1fc6a506488495d951d5263988d25606482015260a0608482015260a48101829052819073a61b8d703a54bd119bcb7904aa68c9a40363cb7f9063128acb089060c40160408051808303816000875af1158015610257573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061027b91906105aa565b9150915060008212801561028e57508581145b801561029a5750600154155b6102d55760405162461bcd60e51b815260206004820152600c60248201526b1c185c9d1a585b08199a5b1b60a21b6044820152606401610112565b6102de826105e4565b92508483101561031b5760405162461bcd60e51b8152602060048201526008602482015267736c69707061676560c01b6044820152606401610112565b5050600080546001600160a01b03191690559392505050565b3373a61b8d703a54bd119bcb7904aa68c9a40363cb7f14801561036157506000546001600160a01b031615155b6103a55760405162461bcd60e51b8152602060048201526015602482015274756e617574686f72697a65642063616c6c6261636b60581b6044820152606401610112565b6000841280156103b55750600083135b80156103c357506001548311155b6103fe5760405162461bcd60e51b815260206004820152600c60248201526b1a5b9d985b1a59081919589d60a21b6044820152606401610112565b82600160008282546104109190610600565b90915550506000546040516323b872dd60e01b81526001600160a01b03909116600482015273a61b8d703a54bd119bcb7904aa68c9a40363cb7f60248201526044810184905273ba876237b0f021a6c6d852d6c26e107997cc5e81906323b872dd906064016020604051808303816000875af1158015610494573d6000803e3d6000fd5b505050506040513d601f19601f820116820180604052508101906104b89190610619565b6104f55760405162461bcd60e51b815260206004820152600e60248201526d1c185e5b595b9d0819985a5b195960921b6044820152606401610112565b50505050565b60008060006060848603121561051057600080fd5b505081359360208301359350604090920135919050565b6000806000806060858703121561053d57600080fd5b8435935060208501359250604085013567ffffffffffffffff81111561056257600080fd5b8501601f8101871361057357600080fd5b803567ffffffffffffffff81111561058a57600080fd5b87602082840101111561059c57600080fd5b949793965060200194505050565b600080604083850312156105bd57600080fd5b505080516020909101519092909150565b634e487b7160e01b600052601160045260246000fd5b6000600160ff1b82016105f9576105f96105ce565b5060000390565b81810381811115610613576106136105ce565b92915050565b60006020828403121561062b57600080fd5b8151801515811461063b57600080fd5b939250505056fea26469706673582212204b891a015d581c15543a1b069be5a0720c81e0b34ca54a47757d53628c6d347264736f6c634300081a0033'
BUYER_SOURCE = '// SPDX-License-Identifier: MIT\npragma solidity 0.8.26;\ninterface IERC20 { function transferFrom(address,address,uint256) external returns(bool); }\ninterface IPool { function swap(address,bool,int256,uint160,bytes calldata) external returns(int256,int256); }\ncontract RonsWhypeBuyer {\n    address public constant WHYPE = 0xbA876237B0F021A6c6D852d6c26E107997cC5E81;\n    address public constant POOL = 0xa61b8d703A54bD119bCB7904aA68C9a40363cb7F;\n    address private payer;\n    uint256 private remaining;\n    function buy(uint256 amountIn, uint256 minimumOut, uint256 deadline) external returns(uint256 output) {\n        require(block.timestamp <= deadline, "expired");\n        require(payer == address(0), "reentrant");\n        require(amountIn > 0 && amountIn <= uint256(type(int256).max), "invalid amount");\n        payer = msg.sender;\n        remaining = amountIn;\n        (int256 d0, int256 d1) = IPool(POOL).swap(msg.sender, false, int256(amountIn),\n            1461446703485210103287273052203988822378723970341, "");\n        require(d0 < 0 && d1 == int256(amountIn) && remaining == 0, "partial fill");\n        output = uint256(-d0);\n        require(output >= minimumOut, "slippage");\n        payer = address(0);\n    }\n    function uniswapV3SwapCallback(int256 d0, int256 d1, bytes calldata) external {\n        require(msg.sender == POOL && payer != address(0), "unauthorized callback");\n        require(d0 < 0 && d1 > 0 && uint256(d1) <= remaining, "invalid debt");\n        remaining -= uint256(d1);\n        require(IERC20(WHYPE).transferFrom(payer, POOL, uint256(d1)), "payment failed");\n    }\n}\n'
FEE = 10000

def fn(name, ins, outs, mut='view'):
    return dict(type='function', name=name, stateMutability=mut,
                inputs=[dict(name='p'+str(i), type=t) for i,t in enumerate(ins)],
                outputs=[dict(type=t) for t in outs])

ERC = [fn('balanceOf',['address'],['uint256']), fn('totalSupply',[],['uint256']),
       fn('allowance',['address','address'],['uint256']),
       fn('approve',['address','uint256'],['bool'],'nonpayable'),
       fn('deposit',[],[],'payable'),fn('withdraw',['uint256'],[],'nonpayable')]
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

class StatusOut:
    """stdout wrapper: status() rewrites one line in place; any other output first
    ends that line, so the last status stays visible above sells, trades and errors."""
    def __init__(self,raw): self.raw=raw;self.width=0
    def status(self,text):
        if not self.raw.isatty(): self.raw.write(text+'\n');self.raw.flush();return
        self.raw.write('\r'+text.ljust(self.width));self.raw.flush();self.width=len(text)
    def end(self):
        if self.width: self.raw.write('\n');self.raw.flush();self.width=0
    def write(self,text):
        if text: self.end()
        return self.raw.write(text)
    def __getattr__(self,name): return getattr(self.raw,name)

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
        from urllib.parse import urlsplit
        # Failover only at startup: one run never mixes nodes (cursor/reorg checks and receipts).
        for i,rpc in enumerate(dict.fromkeys(u for u in (a.rpc,a.rpc_backup) if u)):
            host=urlsplit(rpc).hostname or '?'  # print host only; URLs may carry credentials
            try:
                self.w=Web3(Web3.HTTPProvider(rpc,request_kwargs={'timeout':8}))
                chain=self.w.eth.chain_id
            except Exception as e:
                print('RPC unavailable:',host,type(e).__name__,flush=True);continue
            if chain!=CHAIN: raise RuntimeError('Wrong chain at '+host+': require Elysium 99901')
            print('Using RPC:',host,'(backup)' if i else '(primary)',flush=True)
            break
        else: raise RuntimeError('No RPC reachable (primary and backup)')
        self.addr=account.address if account else None
        def contract(address,abi):
            address=Web3.to_checksum_address(address)
            if not self.w.eth.get_code(address): raise RuntimeError('No contract at '+address)
            return self.w.eth.contract(address=address,abi=abi)
        if a.wrap_only or a.unwrap_all:
            # Standalone wrapping is independent of the RONS pool and buyer contract.
            self.wh=contract(WHYPE,ERC)
            return
        self.token=contract(TOKEN,ERC);self.wh=contract(WHYPE,ERC)
        self.pool=contract(POOL,PAIR);self.factory=contract(FACTORY,FAC)
        self.router=None
        self.deployment_path=a.state_dir/('buyer_v2_'+self.addr.lower()+'.json') if self.addr else None
        if self.addr and self.deployment_path.exists():
            address=json.loads(self.deployment_path.read_text())['address']
            self.router=contract(address,BUYER_ABI)
            if bytes(self.w.eth.get_code(self.router.address)) != bytes.fromhex(BUYER_RUNTIME[2:]):
                raise RuntimeError('Buyer runtime mismatch; refusing approval/trade')
        if self.addr and not self.router and not a.deploy_router:
            raise RuntimeError('Run --deploy-router first: v2 requires a new buyer contract')
        if (self.pool.functions.token0().call().lower()!=TOKEN or
            self.pool.functions.token1().call().lower()!=WHYPE or
            self.pool.functions.fee().call()!=FEE or
            self.pool.functions.factory().call().lower()!=FACTORY or
            self.factory.functions.getPool(self.token.address,self.wh.address,FEE).call().lower()!=POOL):
            raise RuntimeError('Pool identity/fee mismatch')
        self.feed=PriceFeed()

    def observe(self, block=None, sqrt=None):
        usd=self.feed.get();h=self.w.eth.get_block('latest' if block is None else block)
        fresh(h['timestamp'],self.a.max_block_age)
        if sqrt is None: sqrt=self.pool.functions.slot0().call(block_identifier=h['number'])[0]
        supply=self.token.functions.totalSupply().call(block_identifier=h['number'])
        dead=self.token.functions.balanceOf(self.w.to_checksum_address(DEAD)).call(block_identifier=h['number'])
        return cap_from_sqrt(sqrt,usd,supply,dead),usd,h

    def deploy_router(self):
        if self.router: print('Already deployed and verified:',self.router.address);return
        constructor=self.w.eth.contract(abi=BUYER_ABI,bytecode=BUYER_BYTECODE).constructor()
        journal=self.a.state_dir/('deploy_v2_'+self.addr.lower()+'.json')
        if journal.exists(): raise RuntimeError('Deployment attempt exists: inspect journal before retrying')
        rec=self.submit(self.tx(constructor),journal)
        address=rec.contractAddress
        if bytes(self.w.eth.get_code(address))!=bytes.fromhex(BUYER_RUNTIME[2:]):
            raise RuntimeError('Deployed runtime mismatch')
        write_json(self.deployment_path,dict(address=address,chain=CHAIN,pool=POOL),exclusive=True)
        print('Buyer deployed:',address,'Run --prepare next.')

    def ready(self):
        if self.wh.functions.balanceOf(self.addr).call()<self.a.amount_wei:
            raise RuntimeError(f'Need {self.a.amount_hype} WHYPE: run --prepare with the same --amount-hype')
        if self.wh.functions.allowance(self.addr,self.router.address).call()<self.a.amount_wei:
            raise RuntimeError('Need router allowance first: run --prepare')

    def tx(self,function,value=0):
        gas_price=self.w.eth.gas_price
        if gas_price>int(D(str(self.a.max_gwei))*D(10**9)):
            raise RuntimeError('Gas price above configured cap')
        if self.w.eth.get_balance(self.addr)<value+21000*gas_price:
            raise RuntimeError('Insufficient native HYPE: leave additional HYPE for gas')
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
                       wallet=self.addr,chain_id=CHAIN,
                       action='unwrap' if self.a.unwrap_all else 'wrap' if self.a.wrap_only else 'buy_or_setup',
                       token=WHYPE if self.a.wrap_only or self.a.unwrap_all else TOKEN,native_value_wei=tx.get('value',0),
                       amount_whype_wei=self.a.amount_wei,created_at=time.time()),exclusive=True)
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

    def wrap_hype(self,journal):
        # Wrapping is 1:1 with no price or deadline, so an idle chain head is fine here.
        h=self.w.eth.get_block('latest')
        before=self.wh.functions.balanceOf(self.addr).call(block_identifier=h['number'])
        print('WRAP:',self.a.amount_hype,'native HYPE -> WHYPE at',self.wh.address,flush=True)
        rec=self.submit(self.tx(self.wh.functions.deposit(),self.a.amount_wei),journal)
        try:
            after=self.wh.functions.balanceOf(self.addr).call(block_identifier=rec.blockNumber)
            print('WHYPE balance before:',D(before)/D(10**18),
                  'after:',D(after)/D(10**18),flush=True)
        except Exception:
            print('Wrap CONFIRMED; balance refresh unavailable. Do not repeat to refresh.',flush=True)

    def unwrap_all_whype(self,journal):
        # Like wrapping, 1:1 with no price or deadline, so an idle chain head is fine here.
        h=self.w.eth.get_block('latest')
        amount=self.wh.functions.balanceOf(self.addr).call(block_identifier=h['number'])
        if amount==0:
            print('WHYPE balance is zero; nothing sent.',flush=True)
            return
        self.a.amount_wei=amount
        print('UNWRAP ALL:',D(amount)/D(10**18),'WHYPE -> native HYPE on Elysium',flush=True)
        # withdraw burns WHYPE held by msg.sender and returns native HYPE to it.
        # value=0: the WHYPE balance, not native HYPE, is the withdrawal principal.
        rec=self.submit(self.tx(self.wh.functions.withdraw(amount),0),journal)
        try:
            remaining=self.wh.functions.balanceOf(self.addr).call(block_identifier=rec.blockNumber)
            print('Unwrap CONFIRMED. WHYPE remaining:',D(remaining)/D(10**18),flush=True)
        except Exception:
            print('Unwrap CONFIRMED; balance refresh unavailable. Do not repeat to refresh.',flush=True)

    def prepare(self):
        have=self.wh.functions.balanceOf(self.addr).call()
        if have<self.a.amount_wei:
            deficit=self.a.amount_wei-have
            print('Wrapping HYPE:',D(deficit)/D(10**18),flush=True)
            self.submit(self.tx(self.wh.functions.deposit(),deficit),
                        self.a.state_dir/('wrap_v2_'+self.addr.lower()+'_'+str(time.time_ns())+'.json'))
        if self.wh.functions.allowance(self.addr,self.router.address).call()!=self.a.amount_wei:
            self.submit(self.tx(self.wh.functions.approve(self.router.address,self.a.amount_wei)),
                        self.a.state_dir/('approve_v2_'+self.addr.lower()+'_'+str(time.time_ns())+'.json'))
        self.ready();print('Ready:',self.a.amount_hype,'WHYPE and allowance. Run --buy-now or --live with the SAME amount.')

    def buy_now(self,journal):
        # NO USD feed, MC threshold, sell event, or event cursor in manual mode.
        self.ready()
        h=self.w.eth.get_block('latest');fresh(h['timestamp'],self.a.max_block_age)
        # Elysium only makes blocks on activity: the next block is stamped ~now, not head+1s.
        deadline=int(max(h['timestamp'],time.time()))+30
        quote=self.router.functions.buy(self.a.amount_wei,0,deadline).call({'from':self.addr})
        minimum=min_output(quote,self.a.slippage_bps)
        swap=self.router.functions.buy(self.a.amount_wei,minimum,deadline)
        tx=self.tx(swap)
        h=self.w.eth.get_block('latest');fresh(h['timestamp'],self.a.max_block_age)
        if max(h['timestamp'],time.time())>=deadline: raise RuntimeError('Quote expired; run again for a fresh quote')
        print('BUY NOW:',self.a.amount_hype,'WHYPE; minimum RONS',D(minimum)/D(10**18),flush=True)
        self.submit(tx,journal)

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
        deadline=int(max(h['timestamp'],time.time()))+30
        # eth_call executes the real callback/payment in a discarded state, not a transaction.
        quote=self.router.functions.buy(self.a.amount_wei,0,deadline).call({'from':self.addr})
        minimum=min_output(quote,self.a.slippage_bps)
        swap=self.router.functions.buy(self.a.amount_wei,minimum,deadline)
        swap.call({'from':self.addr})
        tx=self.tx(swap)
        cap,usd,latest=self.observe()
        if cap>=THRESHOLD or not self.event_valid(event): return False
        if max(latest['timestamp'],time.time())>=deadline: return False
        print('TRIGGER sell',D(event['sell_wei'])/D(10**18),'WHYPE',event['tx'],
              'cap USD',round(cap,2),'minimum tokens',D(minimum)/D(10**18),flush=True)
        self.submit(tx,journal);return True

def amount_to_wei(text):
    # No float conversion, exponent notation, commas or silent truncation.
    import re
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,18})?',text):
        raise ValueError('Enter a positive decimal, e.g. 0.8; at most 18 decimal places')
    whole,_,fraction=text.partition('.')
    value=int(whole)*10**18+int((fraction or '').ljust(18,'0'))
    if not 0<value<2**255: raise ValueError('Amount must be positive and fit int256')
    return value

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
    assert amount_to_wei('0.8')==800000000000000000
    assert amount_to_wei('0.000000000000000001')==1
    for invalid in ['0','-1','NaN','Infinity','1e2','0.0000000000000000001','0,8']:
        try: amount_to_wei(invalid)
        except ValueError: pass
        else: raise AssertionError('Invalid amount accepted: '+invalid)
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
    modes.add_argument('--buy-now',action='store_true',help='Buy entered amount immediately; ignores MC and sell conditions')
    modes.add_argument('--wrap',dest='wrap_only',action='store_true',help='Wrap native HYPE to WHYPE only; no RONS buy or approve')
    modes.add_argument('--unwrap-all',action='store_true',help='Withdraw all WHYPE to native HYPE on Elysium; no buy/approve')
    modes.add_argument('--init-keystore',type=Path);modes.add_argument('--self-test',action='store_true')
    p.add_argument('--amount-hype',help='Native HYPE to wrap, or WHYPE to spend; prompts if omitted, e.g. 0.8')
    p.add_argument('--keystore',type=Path);p.add_argument('--once',action='store_true')
    p.add_argument('--rpc',default=os.getenv('ELYSIUM_RPC','https://rpc-live.boxa.club'))
    p.add_argument('--rpc-backup',default=os.getenv('ELYSIUM_RPC_BACKUP','https://rpc.ronspad.fun'),
                   help='Used only if --rpc is unreachable at startup; pass "" to disable')
    p.add_argument('--max-event-age',type=int,default=30)
    p.add_argument('--max-block-age',type=int,default=600,
                   help='Max age (s) of the chain head; Elysium only makes blocks on activity')
    p.add_argument('--poll',type=float,default=1);p.add_argument('--slippage-bps',type=int,default=100)
    p.add_argument('--max-gwei',type=D,default=D('2'));p.add_argument('--state-dir',type=Path,default=Path(__file__).resolve().parent/'rons_state')
    a=p.parse_args()
    if a.self_test: self_test();return
    if a.unwrap_all and a.amount_hype is not None: p.error('--unwrap-all uses your full WHYPE balance; omit --amount-hype')
    if not 1<=a.max_event_age<=60 or a.poll<0.2 or not 1<=a.slippage_bps<=300 or a.max_gwei<=0 or not 10<=a.max_block_age<=3600: p.error('Invalid poll/slippage/gas settings')
    a.amount_wei=None
    if a.prepare or a.live or a.buy_now or a.wrap_only:
        prompt='So HYPE muon wrap (vi du 1.2): ' if a.wrap_only else 'So WHYPE muon mua (vi du 0.8): '
        text=a.amount_hype if a.amount_hype is not None else input(prompt).strip()
        try: a.amount_wei=amount_to_wei(text)
        except ValueError as e: p.error(str(e))
        a.amount_hype=format(D(a.amount_wei)/D(10**18),'f')
        print('Selected input:',a.amount_hype,'native HYPE' if a.wrap_only else 'WHYPE',flush=True)
    from eth_account import Account
    if a.init_keystore:
        key=getpass.getpass('Private key (local input, hidden): ')
        account=Account.from_key(key);password=getpass.getpass('New keystore password: ')
        if len(password)<12 or password!=getpass.getpass('Repeat password: '):
            raise RuntimeError('Passwords must match and have at least 12 characters')
        write_json(a.init_keystore,Account.encrypt(account.key,password),exclusive=True)
        print('Encrypted keystore created for',account.address);return
    account=None
    if a.live or a.prepare or a.deploy_router or a.buy_now or a.wrap_only or a.unwrap_all:
        if not a.keystore: p.error('--keystore is required for live/prepare/deploy/buy-now/wrap/unwrap-all')
        key=Account.decrypt(json.loads(a.keystore.read_text()),getpass.getpass('Keystore password: '))
        account=Account.from_key(key);del key
    a.state_dir.mkdir(parents=True,exist_ok=True)
    order_key=account.address.lower() if account else 'dryrun'
    journal=a.state_dir/('rons_'+order_key+'.json')
    lock_path=a.state_dir/('wallet_'+order_key)
    with process_lock(lock_path):
        # A manual order may be repeated only by a NEW explicit invocation after
        # the previous one has a confirmed success/revert, never after uncertainty.
        if account:
            for old in [journal,*a.state_dir.glob('manual_'+order_key+'_*.json'),
                        *a.state_dir.glob('wrap*_'+order_key+'*.json'),
                        *a.state_dir.glob('unwrap*_'+order_key+'*.json'),
                        *a.state_dir.glob('approve*_'+order_key+'*.json'),
                        *a.state_dir.glob('deploy*_'+order_key+'*.json')]:
                if old.exists() and json.loads(old.read_text()).get('status')=='pending':
                    raise RuntimeError('Pending/uncertain order: inspect '+str(old))
        if account and journal.exists() and a.live:
            print('Existing conditional swap attempt; refusing another:',journal.read_text());return
        if a.buy_now:
            journal=a.state_dir/('manual_'+order_key+'_'+str(time.time_ns())+'.json')
        if a.wrap_only:
            journal=a.state_dir/('wrap_only_'+order_key+'_'+str(time.time_ns())+'.json')
        if a.unwrap_all:
            journal=a.state_dir/('unwrap_all_'+order_key+'_'+str(time.time_ns())+'.json')
        buyer=Buyer(a,account)
        if a.unwrap_all: buyer.unwrap_all_whype(journal);return
        if a.wrap_only: buyer.wrap_hype(journal);return
        if a.deploy_router: buyer.deploy_router();return
        if a.prepare: buyer.prepare();return
        if a.buy_now: buyer.buy_now(journal);return
        if a.live: buyer.ready()
        print('LIVE ARMED' if a.live else 'DRY RUN: no transactions',flush=True)
        errors=0;out=sys.stdout=StatusOut(sys.stdout)
        cursor=buyer.w.eth.get_block('latest')
        print('Watching NEW sells after block',cursor['number'],flush=True)
        while True:
            try:
                cap,usd,h=buyer.observe()
                # One status line, rewritten in place; sells, trades and errors print below it.
                out.status(f"block {h['number']} cap USD {round(cap,2)} HYPE/USD {usd}"
                           f"  (checked {time.strftime('%H:%M:%S')})")
                if a.once: out.end();return
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
                    if not a.live: print('Conditional trigger met; dry-run stops without sending.');return
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
    except Exception as e:
        if isinstance(sys.stdout,StatusOut): sys.stdout.end()
        print('STOP:',str(e),file=sys.stderr);sys.exit(1)
