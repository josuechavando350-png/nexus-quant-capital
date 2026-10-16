"""Pinned, unchanged math and evidence primitives from PR11."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'robinhood-prospective-observer-20261016'
sys.path.insert(0, str(PRIOR))
from read_rpc import (need, canonical, qty, header, HASH, MORPHO, MARKET, BORROW,
                      ORACLE, IRM, pinned, NoRedirect, RpcFailure, ENDPOINT)
from model import MARKET_PARAMS, encode, words, screen
from observer import enrollment, Journal


def pin(block):
    return {'blockHash': block['hash'], 'requireCanonical': True}


def view(block, to, data):
    return ('eth_call', [{'to': to, 'data': data}, pin(block)])


def position_data(address):
    return encode('0x93c52062', int(MARKET, 16), int(address, 16))
