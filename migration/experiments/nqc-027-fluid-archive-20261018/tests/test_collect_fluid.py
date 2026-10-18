"""Offline checks of the read-only collector, not observed market opportunities."""
import copy, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'source'))
import collect_fluid as c

def rpc(label, result=None, error=None):
    d={'jsonrpc':'2.0','id':next(x['rpc']['id'] for x in c.plan() if x['label']==label)}
    d['result' if error is None else 'error']=result if error is None else error
    return d

def words(values): return '0x'+''.join(f'{v:064x}' for v in values)

class CollectionTests(unittest.TestCase):
    def test_frozen_plan(self):
        p=c.plan(); self.assertEqual(len(p),c.MAX_CALLS)
        for item in p: c.validate_request(item)
        self.assertEqual([x['rpc']['id'] for x in p],list(range(1,13)))
    def test_no_broadcast(self):
        x=copy.deepcopy(c.plan()[0]);x['rpc']['method']='eth_sendRawTransaction'
        with self.assertRaises(ValueError): c.validate_request(x)
    def test_no_latest(self):
        x=copy.deepcopy(c.plan()[6]);x['rpc']['params'][1]='latest'
        with self.assertRaises(ValueError): c.validate_request(x)
    def test_no_override(self):
        x=copy.deepcopy(c.plan()[6]);x['rpc']['params'].append({c.EXECUTOR:{'balance':'0xffff'}})
        with self.assertRaises(ValueError): c.validate_request(x)
    def test_wrong_quote_selector(self):
        with self.assertRaises(ValueError): c.interpret('quote',rpc('quote',error={'code':3,'data':'0xdeadbeef'+'0'*64}))
    def test_quote_is_not_trade(self):
        q=c.interpret('quote',rpc('quote',error={'code':3,'data':'0xb3bfda99'+f'{26409680973611000000:064x}'}))
        self.assertEqual(q['amount_out_wei'],'26409680973611000000')
        self.assertEqual(q['hypothetical_residual_historical_bid_and_gas_wei'],'1651296044494913')
        self.assertFalse(q['settlement_verified']); self.assertIsNone(q['all_cost_nqc_profit_wei'])
    def test_success_result_is_not_dead_quote(self):
        with self.assertRaises(ValueError): c.interpret('quote',rpc('quote',result=words([1])))
    def test_wrong_pool_mapping(self):
        w=[0]*18;w[0]=21;w[1]=int(c.LIQ,16);w[9]=int(c.EZETH,16);w[10]=int(c.NATIVE,16)
        self.assertIn('MATCH',c.interpret('constants',rpc('constants',result=words(w)))['status'])
        w[10]=int(c.EZETH,16)
        with self.assertRaises(ValueError):c.interpret('constants',rpc('constants',result=words(w)))
    def test_wrong_chain_or_null(self):
        for value in ['0xa',None]:
            with self.assertRaises(ValueError):c.interpret('chain',rpc('chain',result=value))
    def test_correlation_and_ambiguous_response(self):
        v=rpc('quote',error={'code':3,'data':'0xb3bfda99'+'0'*64});v['id']=1
        with self.assertRaises(ValueError): c.interpret('quote',v)
        v=rpc('chain',result='0x1');v['error']={'code':-1}
        with self.assertRaises(ValueError): c.interpret('chain',v)
    def test_no_second_attempt_or_other_repo(self):
        with patch.dict(os.environ,{'GITHUB_REPOSITORY':c.REPO,'GITHUB_REF':'refs/heads/'+c.BRANCH,'GITHUB_RUN_ATTEMPT':'2'},clear=True):
            with self.assertRaises(ValueError): c.collect(Path('/unused'))
    def test_stop_on_first_transport_error_no_retry(self):
        class Failed:
            def open(self,*args,**kwargs):raise OSError('offline test, no connection made')
        env={'GITHUB_REPOSITORY':c.REPO,'GITHUB_REF':'refs/heads/'+c.BRANCH,'GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'a'*40}
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,env,clear=True),patch.object(c,'build_opener',return_value=Failed()),patch('builtins.print'):
            r=c.collect(Path(t)/'result')
            self.assertEqual(r['requests_attempted'],1);self.assertEqual(r['retries'],0)
            self.assertEqual(r['status'],'BLOCKED_NO_RETRY');self.assertFalse(r['nqc_opportunity_proven'])
    def test_byte_precision_rejects_truncation(self):
        for v in ['0x',words([1,2,3]),words([1,2,3,0]),None]:
            with self.assertRaises(ValueError):c.interpret('precisions',rpc('precisions',result=v))
    def test_target_prefix_identity(self):
        v={'hash':c.TARGET,'number':hex(26190955),'timestamp':hex(1791983495),'parentHash':c.PARENT,'stateRoot':'0x'+'0'*64,'transactions':[c.TX0,c.TX]}
        self.assertIn('MATCH',c.interpret('target_header',rpc('target_header',result=v))['status'])
        v['transactions'].reverse()
        with self.assertRaises(ValueError):c.interpret('target_header',rpc('target_header',result=v))

if __name__=='__main__':unittest.main()
