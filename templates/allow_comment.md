### Beacon Connectivity Verdict — Allow

**Decision** `{{ verdict.decisionId }}` · signed under `{{ verdict.policyBundle }}`
**Source** `{{ source.workloadId }}` in `{{ source.namespace }}` ({{ source.cluster }}, {{ source.ownerTeam }}, {{ source.complianceDomain }})
**Destination** `{{ destination.requestedFqdn }}` → `{{ destination.serviceId }}` ({{ destination.ownerTeam }}, {{ destination.dataClassification }}, {{ destination.complianceDomain }})
**TTL** {{ lifecycle.requestedTtlDays }} days · expires `{{ verdict.expiresAt }}`
**Implementation hash** `{{ verdict.implementationHash }}`

{% if controls.primary %}#### Controls

| Type | Owner | Target |
| --- | --- | --- |
| **{{ controls.primary.type }}** (primary) | {{ controls.primary.owner }} | {{ controls.primary.target }}{% for t in controls.transitive %}
| {{ t.type }} | {{ t.owner }} | {{ t.target }}{% endfor %}

{% endif %}{% if verdict.matchedRules %}#### Matched rules

{% for r in verdict.matchedRules %}- `{{ r }}`
{% endfor %}

{% endif %}**Evidence artifacts** (signed verdict + derived intent + enrichment snapshot): attached to this workflow run as `beacon-evidence`.

**Durable approval record**: `.beacon/approvals/{{ verdict.canonicalRequest.metadata.name }}.yaml` will be committed to `main` automatically when this PR merges.
