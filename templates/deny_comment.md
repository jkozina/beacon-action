### Beacon Connectivity Verdict — Deny

**Decision** `{{ verdict.decisionId }}` · signed under `{{ verdict.policyBundle }}`
**Destination** `{{ destination.requestedFqdn }}` → `{{ destination.serviceId }}` ({{ destination.dataClassification }}, {{ destination.complianceDomain }})

#### Why this was denied

{% for d in denyReasons %}**`{{ d.id }}`** — {{ d.message }}

{% endfor %}

#### How to fix

{% if denyReasons | selectattr('id', 'equalto', 'TTL_EXCEEDS_MAX') | list %}- Reduce `egress.allow[0].ttlDays` in `charts/orders/values.yaml` (current request: {{ lifecycle.requestedTtlDays }}, max allowed: 30 for restricted destinations), **or**
- Open an exception with `{{ destination.ownerTeam }}` referencing decision `{{ verdict.decisionId }}`.
{% else %}- See the deny reason(s) above. Consult the destination owner (`{{ destination.ownerTeam }}`) or your platform team.
{% endif %}

Implementation: hash `{{ verdict.implementationHash }}`.
