"""NQC016: bounded local study of gross sponsor payment versus fixed return.
No signatures, remote chain RPC, production transfers, secret access or writes.
A no-return cash surplus is NOT operator profit and is NOT provider permission.
"""
from pathlib import Path
import argparse, base64, copy, gzip, hashlib, importlib, io, json, os, subprocess, sys, tarfile, traceback, unittest

REPO = 'josuechavando350-png/nexus-quant-capital'
PRODUCER_BASE = '6da36867faad9f915355188dbefd890a7498d93f'
ASTRA_BASE = 'f9d876990a85e55ba196702c32fe3668b49fda71'
BRANCH = 'refs/heads/research/nqc-016-settlement-envelope-20261017'
MARKER = 'NQC016_APPROVED_LOCAL_SETTLEMENT_ONCE'
HERE = Path(__file__).resolve().parent
E = 10**18


def amount(value):
    if type(value) is not int or value < 0 or value >= 2**256:
        raise ValueError('nonnegative uint256 integer required')
    return value


def decision(row, *, surplus_terms_verified=None, no_recourse_verified=None,
             extra_costs_wei=None, provider_accepted=None):
    """A measured cash delta is after the included proposer transfer, not profit.
    Missing external terms can NEVER become a commercial PASS.
    """
    for key in ('advance_wei', 'retained_financing_wei', 'nqc_new_weth_wei',
                'proposer_paid_wei', 'proposer_required_wei'):
        amount(row[key])
    if type(row['builder_cash_delta_wei']) is not int:
        raise ValueError('signed integer cash delta required')
    for value in (surplus_terms_verified, no_recourse_verified, provider_accepted):
        if value is not None and type(value) is not bool:
            raise ValueError('tri-state evidence required')
    if extra_costs_wei is not None:
        amount(extra_costs_wei)
    failures = []
    if not row['business_completed']: failures.append('business_not_completed')
    if row['unexpected_inclusion']: failures.append('unexpected_or_missing_transaction')
    if row['nqc_new_weth_wei'] <= 0: failures.append('no_new_operator_weth')
    if row['proposer_paid_wei'] != row['proposer_required_wei']:
        failures.append('proposer_payment_not_settled')
    if row['builder_cash_delta_wei'] <= 0: failures.append('builder_cash_not_positive')
    if extra_costs_wei is not None and row['builder_cash_delta_wei']-extra_costs_wei <= 0:
        failures.append('builder_margin_not_positive_after_known_costs')
    if no_recourse_verified is False: failures.append('nonrecourse_requirement_not_met')
    if surplus_terms_verified is False: failures.append('settlement_terms_not_met')
    if provider_accepted is False: failures.append('provider_rejected')
    known = all(x is True for x in (surplus_terms_verified, no_recourse_verified, provider_accepted))
    # Synthetic market data independently precludes commercial certification.
    return {'local_cash_status': 'REFUTED_UNDER_ASSUMPTIONS' if failures else 'MODEL_ONLY_FAVORABLE',
            'failures': failures, 'retained_financing_not_income_wei': row['retained_financing_wei'],
            'complete_net_profit_wei': None if extra_costs_wei is None else row['builder_cash_delta_wei']-extra_costs_wei,
            'external_terms_complete': known, 'commercial_admission': False,
            'surplus_terms_verified': surplus_terms_verified, 'no_recourse_verified': no_recourse_verified,
            'provider_accepted': provider_accepted, 'historical_state_verified': False}


class PolicyTests(unittest.TestCase):
    def row(self):
        return dict(advance_wei=100, retained_financing_wei=60, nqc_new_weth_wei=20,
                    proposer_paid_wei=40, proposer_required_wei=40, builder_cash_delta_wei=10,
                    business_completed=True, unexpected_inclusion=False)
    def test_01_positive_cash_not_commercial(self):
        r=decision(self.row());self.assertEqual(r['local_cash_status'],'MODEL_ONLY_FAVORABLE');self.assertFalse(r['commercial_admission'])
    def test_02_unknown_costs_not_zero(self): self.assertIsNone(decision(self.row())['complete_net_profit_wei'])
    def test_03_retained_cash_not_income(self): self.assertEqual(decision(self.row())['retained_financing_not_income_wei'],60)
    def test_04_builder_loss_rejected(self):
        r=self.row();r['builder_cash_delta_wei']=-1;self.assertIn('builder_cash_not_positive',decision(r)['failures'])
    def test_05_zero_margin_rejected(self):
        r=self.row();r['builder_cash_delta_wei']=0;self.assertTrue(decision(r)['failures'])
    def test_06_missing_proposer_payment(self):
        r=self.row();r['proposer_paid_wei']=0;self.assertIn('proposer_payment_not_settled',decision(r)['failures'])
    def test_07_incomplete_business(self):
        r=self.row();r['business_completed']=False;self.assertTrue(decision(r)['failures'])
    def test_08_pending_transaction(self):
        r=self.row();r['unexpected_inclusion']=True;self.assertTrue(decision(r)['failures'])
    def test_09_explicit_liability(self): self.assertTrue(decision(self.row(),no_recourse_verified=False)['failures'])
    def test_10_costs_exhaust_margin(self): self.assertTrue(decision(self.row(),extra_costs_wei=10)['failures'])
    def test_11_one_wei_survives(self): self.assertEqual(decision(self.row(),extra_costs_wei=9)['complete_net_profit_wei'],1)
    def test_12_even_hypothetical_terms_not_commercial(self):
        r=decision(self.row(),surplus_terms_verified=True,no_recourse_verified=True,provider_accepted=True,extra_costs_wei=0)
        self.assertTrue(r['external_terms_complete']);self.assertFalse(r['commercial_admission'])
    def test_13_reject_float(self):
        r=self.row();r['advance_wei']=1.0
        with self.assertRaises(ValueError):decision(r)
    def test_14_reject_boolean_amount(self):
        r=self.row();r['retained_financing_wei']=True
        with self.assertRaises(ValueError):decision(r)
    def test_15_reject_invalid_terms(self):
        with self.assertRaises(ValueError):decision(self.row(),provider_accepted='yes')
    def test_16_cost_unknown_does_not_hide_bad_input(self):
        r=self.row();r['proposer_paid_wei']=-1
        with self.assertRaises(ValueError):decision(r)


def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')


def run_matrix(repo,anvil,artifacts,compiled_dir,out,previous):
    base=repo/'migration/experiments/nqc-sponsored-bundle-gate-20261017'
    sys.path.insert(0,str(base));ln=importlib.import_module('local_node');rc=importlib.import_module('run_coordinated')
    ln.HERE=out;ln.ref.HERE=out
    art=json.loads(artifacts.read_text());compiled=json.loads((compiled_dir/'compiled_contracts.json').read_text())
    lock=json.loads((base/'SOURCE_LOCK.json').read_text())['bytecode']['bytecode_sha256']
    for n,h in lock.items():assert hashlib.sha256(bytes.fromhex(art[n]['bytecode'][2:])).hexdigest()==h
    assert json.loads((compiled_dir/'status.json').read_text())['compiled'] is True
    out.mkdir(exist_ok=False);(out/'evidence').mkdir()
    specs=[('control_fixed_return',3*10**16,4*10**16,True,False,False),
           ('gross_002',2*10**16,4*10**16,False,False,False),
           ('gross_003',3*10**16,4*10**16,False,False,False),
           ('gross_004',4*10**16,4*10**16,False,False,False),
           ('gross_006_loss',6*10**16,4*10**16,False,False,False),
           ('gross_010_loss',10**17,4*10**16,False,False,False),
           ('gross_insufficient_start',10**15,4*10**16,False,False,False),
           ('gross_larger_proposer_payment',3*10**16,7*10**16,False,False,False),
           ('gross_wrong_header',3*10**16,4*10**16,False,True,False),
           ('gross_high_gas',3*10**17,4*10**16,False,False,True)]
    rows=[]
    with ln.node(str(anvil),copy.deepcopy(art),pool_override=True) as lab:
        lab.setup();save(out/'evidence/setup.json',{'report':lab.setup_report,'transactions':lab.setup_records})
        for name,A,P,fixed,wrong,high in specs:
            snapshot=lab.rpc('evm_snapshot');actors=dict(lab.actors)
            try:
                builder=actors['simulated_builder'];op=actors['nqc_sender_and_beneficiary'];proposer=actors['proposer']
                lab.actors['sponsor_and_topup_financier']=builder
                lab.rpc('anvil_setBalance',[builder,hex(100*E)])
                lab.coinbase=proposer if wrong else builder;lab.rpc('anvil_setCoinbase',[lab.coinbase])
                lab.art=copy.deepcopy(art);lab.art['NqcMorphoSponsoredLiquidation']=compiled['NqcMorphoSponsoredLiquidationPaymentLayout']
                base_fee=(20 if high else 1)*10**9
                requests=[x for x in rc.build_package(lab,advance=A,base_fee=base_fee)
                          if x['label']!='separate_builder_fee' and (fixed or x['label']!='return_unused_advance')]
                for t in requests:
                    if t['label']=='liquidate':
                        d=previous.decode_raw(bytes.fromhex(t['request']['data'][2:]),new=False)
                        t['request']['data']='0x'+previous.encode_raw(d.words+(int(builder,16),1),d.collateral_route,d.weth_route,new=True).hex()
                # Independent lab proposer payment: NOT a quote or promise by Titan.
                requests.append({'label':'builder_pays_proposer','request':{'from':builder,'to':proposer,'data':'0x',
                    'value':hex(P),'nonce':'0x1','gas':hex(21000),'maxFeePerGas':hex((30 if high else 3)*10**9),
                    'maxPriorityFeePerGas':hex(10**9)}})
                if fixed:
                    snap=lab.rpc('evm_snapshot');trial=rc.execute_block(lab,requests,base_fee,name+'_planning',observe=False)
                    qcost=sum(t['gas_cost_wei'] for t in trial['transactions'] if t['request']['from']==op)
                    assert lab.rpc('evm_revert',[snap])
                    for t in requests:
                        if t['label']=='return_unused_advance':t['request']['value']=hex(A-qcost)
                r=rc.execute_block(lab,requests,base_fee,name)
                r.update(architecture='C1',settlement_model='EXACT_RETURN_CONTROL' if fixed else 'GROSS_PAYMENT_WITH_UNRESOLVED_SURPLUS',
                         advance_wei=A,proposer_payment_assumed_wei=P,surplus_owner_rights=None,provider_terms=None,
                         provider_acceptance=False,fixture_cash_wei=0)
                save(out/'evidence'/f'{name}.json',r)
                native=previous.check_native(r);previous.check_tokens(r)
                tx={t['label']:t for t in r['transactions']}
                for t in r['transactions']:
                    q=t['request'];receipt=t['receipt'];sender=q['from']
                    reserve=int(q['gas'],16)*int(q['maxFeePerGas'],16)+int(q['value'],16)
                    assert t['before'][sender]['ETH']>=reserve
                    assert int(receipt['gasUsed'],16)<=int(q['gas'],16)
                    assert int(receipt['effectiveGasPrice'],16)==min(int(q['maxFeePerGas'],16),base_fee+int(q['maxPriorityFeePerGas'],16))
                prefix_spent=0;min_start=0
                for t in r['transactions']:
                    q=t['request']
                    if q['from']==op:
                        min_start=max(min_start,prefix_spent+int(q['gas'],16)*int(q['maxFeePerGas'],16)+int(q['value'],16))
                        prefix_spent+=t['gas_cost_wei']+int(q['value'],16)
                if name!='gross_insufficient_start':
                    for label in ('nqc_adapter','nqc_executor'):
                        assert int(tx[label]['receipt']['status'],16)==1
                        assert lab.rpc('eth_getCode',[lab.actors[label],'latest'])!='0x'
                closed=r['final']['position'][1]==0
                expect_closed=name not in ('gross_wrong_header','gross_insufficient_start')
                assert closed==expect_closed,(name,'wrong debt outcome')
                if closed:
                    assert r['final']['balances'][op]['WETH']==159365645570551238
                    assert int(tx['liquidate']['receipt']['status'],16)==1
                    payments=[p for p in native['executor_payments'] if p['to']==builder]
                    assert len(payments)==1 and payments[0]['value']==9*10**16
                    assert lab.token(lab.actors['WETH'],lab.actors['Morpho'])==8*E
                if wrong:
                    assert int(tx['liquidate']['receipt']['status'],16)==0
                    assert tx['liquidate']['trace'].get('output')=='0x'+previous.keccak256(b'InvalidPlan()')[:4].hex()
                bid=tx['builder_pays_proposer'];assert int(bid['receipt']['status'],16)==1
                assert bid['trace']['from']==builder and bid['trace']['to']==proposer
                assert int(bid['trace']['value'],16)==P
                if fixed:assert r['final']['balances'][op]['ETH']==0
                else:assert 'return_unused_advance' not in tx
                qgas=sum(t['gas_cost_wei'] for t in r['transactions'] if t['request']['from']==op)
                if not fixed:assert r['final']['balances'][op]['ETH']==A-qgas
                row=dict(case=name,advance_wei=A,proposer_required_wei=P,proposer_paid_wei=P,
                    builder_cash_delta_wei=native['native_net'].get(builder,0),
                    retained_financing_wei=r['final']['balances'][op]['ETH'],nqc_new_weth_wei=r['final']['balances'][op]['WETH'],
                    business_completed=closed,unexpected_inclusion=bool(r['accepted_not_included'] or r['rpc_rejections']),
                    minimum_start_for_observed_prefixes_wei=min_start,
                    gas_total=sum(int(t['receipt']['gasUsed'],16) for t in r['transactions']),included=len(r['transactions']),
                    legacy_return_required_flag=r['flags']['EVM_LOCAL_PASS'],
                    native_payment_wei=9*10**16 if closed else 0,net_proposer_payment_real_unknown=True)
                row['policy']=decision(row)
                expected_negative=name in ('gross_006_loss','gross_010_loss','gross_insufficient_start',
                                           'gross_larger_proposer_payment','gross_wrong_header','gross_high_gas')
                assert (row['policy']['local_cash_status']=='REFUTED_UNDER_ASSUMPTIONS')==expected_negative,(name,row)
                row['assertions_passed']=True;rows.append(row)
                save(out/'evidence'/f'{name}_reconciled.json',{'row':row,'native':native})
                print('NQC016_CASE '+json.dumps(row,sort_keys=True),flush=True)
            finally:
                assert lab.rpc('evm_revert',[snapshot]);lab.actors=actors
    byname={x['case']:x for x in rows}
    for low,high in (('gross_002','gross_003'),('gross_003','gross_004')):
        a,b=byname[low],byname[high];difference=b['advance_wei']-a['advance_wei']
        assert a['gas_total']==b['gas_total'] and a['nqc_new_weth_wei']==b['nqc_new_weth_wei']
        assert a['builder_cash_delta_wei']-b['builder_cash_delta_wei']==difference
        assert b['retained_financing_wei']-a['retained_financing_wei']==difference
    result={'status':'TEN_LOCAL_SETTLEMENT_CONTROLS_PASS','rows':rows,'node_stopped':True,
            'total_receipts':sum(x['included'] for x in rows),'commercial_admission':False,
            'historical_replay':False,'provider_acceptance':None,'surplus_rights':None,'no_recourse':None}
    save(out/'summary.json',result)
    return result


def export(out,status):
    save(out/'execution_status.json',status)
    print('NQC016_STATUS_BEGIN\n'+json.dumps(status,sort_keys=True)+'\nNQC016_STATUS_END',flush=True)
    bundle={}
    for p in sorted(out.rglob('*')):
        if p.is_file() and p.suffix in ('.json','.log','.txt'):
            raw=p.read_bytes();assert len(raw)<4000000
            bundle[str(p.relative_to(out))]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'text':raw.decode()}
    gz=gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0);assert len(gz)<900000
    print('NQC016_EXPORT_META '+json.dumps({'files':len(bundle),'gzip_bytes':len(gz),'gzip_sha256':hashlib.sha256(gz).hexdigest()}))
    encoded=base64.b64encode(gz).decode();print('NQC016_EVIDENCE_GZIP_BASE64_BEGIN')
    for i in range(0,len(encoded),10000):print(encoded[i:i+10000])
    print('NQC016_EVIDENCE_GZIP_BASE64_END',flush=True)


def main():
    if '--unit' in sys.argv:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(PolicyTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 2
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ['GITHUB_REF']==BRANCH
    assert os.environ['GITHUB_RUN_ATTEMPT']=='1' and event['head_commit']['message']==MARKER
    assert event['repository']['id']==1411047452 and event['repository']['full_name']==REPO and event['repository']['private'] is False
    producer=HERE.parents[2]
    assert subprocess.check_output(['git','-C',str(producer),'rev-parse','HEAD'],text=True).strip()==os.environ['GITHUB_SHA']
    previous_path=HERE.parent/'nqc-015-local-evm-20261017';comp=HERE.parent/'nqc-013-compile-only-20261017'
    sys.path.insert(0,str(previous_path));old=importlib.import_module('ci_evm')
    work=Path(os.environ['RUNNER_TEMP'])/'nqc016';work.mkdir(exist_ok=False);out=work/'evidence';out.mkdir()
    status={'status':'INCOMPLETE_OR_FAILED','compiled':False,'evm_completed':False,'commercial_admission':False,
            'producer_sha':os.environ['GITHUB_SHA'],'producer_base':PRODUCER_BASE,'run_id':os.environ['GITHUB_RUN_ID']}
    try:
        old.run([sys.executable,HERE/'experiment.py','--unit'])
        repo=work/'base';old.run(['git','init','-q',repo]);old.run(['git','-C',repo,'remote','add','origin','https://github.com/'+REPO+'.git'])
        old.run(['git','-C',repo,'fetch','--depth=1','origin',ASTRA_BASE]);old.run(['git','-C',repo,'checkout','--detach','FETCH_HEAD'])
        assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==ASTRA_BASE
        artifacts=old.recover(repo,out)
        compiler=work/'solc';raw=old.download('https://binaries.soliditylang.org/linux-amd64/solc-linux-amd64-v0.8.24+commit.e11b9ed9',20000000)
        assert old.digest(raw)==old.SOLC_SHA;compiler.write_bytes(raw);compiler.chmod(0o700)
        prov=json.loads((repo/'migration/experiments/morpho-sponsor-e2e-20261017/evidence/anvil-provenance.json').read_text())
        raw=old.download(prov['registry_url'],50000000)
        assert 'sha512-'+base64.b64encode(hashlib.sha512(raw).digest()).decode()==prov['integrity']
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tf:
            members=[m for m in tf.getmembers() if m.isfile() and m.name.endswith('/bin/anvil')]
            assert len(members)==1 and members[0].size<100000000
            binary=tf.extractfile(members[0]).read()
        assert old.digest(binary)==old.ANVIL_SHA
        anvil=work/'anvil';anvil.write_bytes(binary);anvil.chmod(0o700)
        sys.path.insert(0,str(comp));previous=importlib.import_module('run_local_matrix')
        old.run([sys.executable,comp/'prepare_compile.py','--out',out/'compilation','--solc',compiler,'--solc-sha256',old.SOLC_SHA])
        status['compiled']=json.loads((out/'compilation/status.json').read_text())['compiled']
        summary=run_matrix(repo,anvil,artifacts,out/'compilation',out/'evm',previous)
        old.run(['git','-C',repo,'diff','--exit-code','HEAD']);old.run(['git','-C',producer,'diff','--exit-code','HEAD'])
        status.update(status=summary['status'],evm_completed=True,results=summary['rows'],receipts=summary['total_receipts'],
                      node_stopped=True,new_unit_tests=16,solc_sha256=old.SOLC_SHA,anvil_sha256=old.ANVIL_SHA)
    except Exception as exc:
        status.update(error_type=type(exc).__name__,error=str(exc));traceback.print_exc()
    finally:export(out,status)
    return 0 if status['evm_completed'] else 2

if __name__=='__main__':sys.exit(main())
