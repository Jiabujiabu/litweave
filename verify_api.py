"""Explicit local-operator smoke test. Keys stay in memory, never in argv/output."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from model_access import user_access
from model_registry import provider_config, model_preset
from connection_check import verify_generation


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',choices=['deepseek','openai','anthropic'],required=True)
    parser.add_argument('--model',required=True)
    parser.add_argument('--confirm-small-api-charge',action='store_true')
    parser.add_argument('--output-limit',type=int,default=32)
    parser.add_argument('--output',default='.research_runs/real_api_validation/latest.json')
    args=parser.parse_args()
    if not args.confirm_small_api_charge:
        parser.error('This sends one real request and may incur a small API charge. Explicit confirmation is required.')
    cfg=provider_config(args.provider)
    values=dotenv_values(Path(__file__).parent/'.env')
    key=(values.get(cfg['key_env']) or '').strip()
    if not key or key=='your_key_here':
        print(json.dumps({'status':'not_verified','provider':args.provider,'reason':'no_local_user_key'}))
        return 2
    preset=model_preset(args.provider,args.model)
    access=user_access(args.provider,args.model,key,display_name=preset['display_name'] if preset else args.model)
    result=verify_generation(access,consent=True,output_limit=args.output_limit,timeout=60)
    result['verified_at_utc']=datetime.now(timezone.utc).isoformat()
    result['credential_source']='explicit_local_operator_environment'
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get('generation_verified') else 1


if __name__=='__main__':
    raise SystemExit(main())
