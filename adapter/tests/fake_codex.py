"""Protocol fixture only. No API, emulator, or credentials."""
import json
import sys

thread_count=0
turn_count=0
for line in sys.stdin:
    request=json.loads(line); method=request.get("method"); rid=request.get("id")
    if method=="initialized": continue
    if method=="initialize": result={"userAgent":"fixture"}
    elif method=="thread/start":
        thread_count+=1
        assert request["params"]["sandbox"]=="read-only"
        result={"thread":{"id":f"fixture-thread-{thread_count}"}}
    elif method=="turn/start":
        turn_count+=1
        result={"turn":{"id":f"turn-{turn_count}","status":"inProgress"}}
    else: raise ValueError("unexpected_fixture_request")
    print(json.dumps({"id":rid,"result":result}),flush=True)
    if method=="turn/start":
        params={"threadId":"fixture-thread-1","turnId":f"turn-{turn_count}"}
        print(json.dumps({"method":"item/completed","params":{**params,"item":{"id":"r","type":"reasoning","text":"PRIVATE_REASONING_NOT_AN_IDEA_LOG"}}}),flush=True)
        plan={"objective":"Fixture progress","rationale":"Returned fixture rationale","guidance":"Fixture only",
            "review_after_frames":48,"milestones":[],
            "stages":[{'id':'test','kind':'custom','objective':'Fixture progress','guidance':'Fixture only',
                'target':'synthetic target','region':None,'grounded':None}]}
        print(json.dumps({"method":"item/completed","params":{**params,"item":{"id":"a","type":"agentMessage","phase":"final_answer","text":json.dumps(plan)}}}),flush=True)
        print(json.dumps({"method":"thread/tokenUsage/updated","params":{**params,"tokenUsage":{"last":{"inputTokens":10,"outputTokens":20}}}}),flush=True)
        print(json.dumps({"method":"turn/completed","params":{**params,"turn":{"id":f"turn-{turn_count}","status":"completed"}}}),flush=True)
