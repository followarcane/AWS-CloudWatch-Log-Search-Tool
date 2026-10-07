# Roadmap — multi-team platform (Future B)

v1/v2 ships a solid **desktop** log searcher. The items below are the company platform backlog.

## Priority order

1. **Shared catalog service**  
   Central path/profile catalog (S3 or Git). App pulls on launch and caches locally. Reduces drift from hand-edited `config.company.json`.

2. **Team / env visibility**  
   Tag envs/paths by team in the catalog. UI only lists what the user’s config allows. **AWS IAM remains the real security boundary.**

3. **Search history & saved searches**  
   Local SQLite first; optional later sync for shared saved queries.

4. **Shareable deep links**  
   e.g. `logsearcher://env=PROD&q=orderId&start=3h` or an exportable search bundle for Slack.

5. **Backend upgrade: boto3**  
   Replace `awslogs` CLI with `FilterLogEvents` and/or CloudWatch Logs Insights for better pagination, typed errors, and fewer process edge cases.

6. **Observability**  
   Optional anonymous usage metrics + crash reporter (privacy-reviewed).

7. **Windows parity + auto-update**  
   Signed Windows build; Sparkle (macOS) / similar updater.

8. **Internal web variant (optional)**  
   Same core search API behind SSO if the company later prefers browser delivery.

## Explicitly out of current desktop v2

- Server-side SSO proxy
- Shared live collaboration on a search session
- Full Logs Insights query builder UI
