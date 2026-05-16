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

{% endif %}Evidence artifacts: derived-intent · enrichment-snapshot · canonical-request · signed verdict. See workflow artifacts.
