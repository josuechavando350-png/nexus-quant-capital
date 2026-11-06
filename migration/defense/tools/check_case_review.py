"""Exercise authenticated local review of a real preserved fixture bundle."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.case_evidence import capture_case
from nqc_defense.case_review import CaseReview, ORIGIN
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore
from nqc_defense.review_policy import ReviewPolicy, read_credential


def run():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); log = root / "auth.jsonl"
        log.write_bytes(b"".join(canonical({"schema":"nqc-auth-log-v1","time_ns":i*1000000000,
            "outcome":"failure","principal":"fixture-user","remote_address":"192.0.2.50"}) + b"\n" for i in range(3)))
        store = OperationsStore.create(root / "operations")
        monitor = AuthLogMonitor.register(store,"auth","evaluation","host",root,log.name,3,60)
        monitor.poll(); case = store.cases("evaluation","host")[0]; case_digest=sha256(canonical(case))
        bundle_path=root / "bundle.json"
        evidence=capture_case(store,"evaluation","host",case["case_id"],case_digest,monitor.digest,
                              [{"generation":0,"name":log.name}],bundle_path)
        grants=[{"actor":actor,"tenant":"evaluation","assets":["host"],"permissions":permissions}
                for actor,permissions in [("analyst",["read","start","note","assess"]),
                                          ("confirmer",["read","close","reopen"]),("observer",["read"])]]
        policy=ReviewPolicy.create(root / "review-policy",grants)
        keys={g["actor"]:read_credential(policy.root / "credentials" / (g["actor"]+".key")) for g in grants}
        review=CaseReview(store,policy); head=dict(ORIGIN); timeline=[]
        def act(actor,action,request,verdict=None):
            nonlocal head
            result=review.apply(actor,keys[actor],"evaluation","host",case["case_id"],action,"Explicit fixture review",request,head,
                bundle_path.read_bytes(),evidence["bundle_digest"],case_digest,monitor.digest,verdict=verdict)
            head=result["checkpoint"]; timeline.append({"action":action,"actor":actor,"stage":result["review"]["stage"],"revision":head["revision"]})
            return result
        act("analyst","start","start")
        before_note=dict(head); note=act("analyst","note","note")
        retry=review.apply("analyst",keys["analyst"],"evaluation","host",case["case_id"],"note","Explicit fixture review","note",before_note,
                           bundle_path.read_bytes(),evidence["bundle_digest"],case_digest,monitor.digest)
        if retry["applied"] or retry["checkpoint"] != note["checkpoint"]:
            raise AssertionError("retry duplicated a review action")
        act("analyst","assess","needs_response", "needs_response")
        try:
            act("confirmer","close","blocked_close")
        except Rejected as exc:
            response_closure_rejection=str(exc)
        else:
            raise AssertionError("case requiring response was closed")
        act("analyst","assess","benign","benign")
        closed=act("confirmer","close","confirm")
        if closed["review"]["stage"] != "closed":
            raise AssertionError("confirmation did not close review")
        reopened=act("confirmer","reopen","reopen")
        if reopened["review"]["assessment"] is not None:
            raise AssertionError("reopening retained an obsolete assessment")
        retained=dict(head)
        view=review.view("observer",keys["observer"],"evaluation","host",case["case_id"],expected=retained)
        if view["detection_status"] != "open" or view["review"]["stage"] != "investigating":
            raise AssertionError("review changed the underlying detection")
        with store.transaction() as db:
            db.execute("DELETE FROM case_reviews WHERE revision=?",(retained["revision"],))
        try:
            review.view("observer",keys["observer"],"evaluation","host",case["case_id"],expected=retained)
        except Rejected as exc:
            truncation_rejection=str(exc)
        else:
            raise AssertionError("truncated history matched retained checkpoint")
        return {"verified":True,"fixture_origin":"authored authentication records and local review credentials in temporary files",
                "timeline":timeline,"evidence_bundle_digest":evidence["bundle_digest"],"policy_digest":policy.digest,
                "retained_checkpoint":retained,"idempotent_retry_verified":True,
                "response_required_closure_rejected":response_closure_rejection,"history_truncation_rejected":truncation_rejection,
                "detection_status_unchanged":True,"credentials_or_keys_in_report":False,
                "human_identity_verified":False,"independent_anchor":False,"production_activated":False}


if __name__ == "__main__":
    print(json.dumps(run(),indent=2,sort_keys=True))
