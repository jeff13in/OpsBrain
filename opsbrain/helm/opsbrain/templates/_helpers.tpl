{{/* Common labels for every object. */}}
{{- define "opsbrain.labels" -}}
app.kubernetes.io/part-of: opsbrain
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* Selector labels for one service; `app` matches the legacy k8s/ manifests. */}}
{{- define "opsbrain.selectorLabels" -}}
app: {{ .name }}
app.kubernetes.io/name: {{ .name }}
{{- end -}}

{{/* Fully qualified image for one service. */}}
{{- define "opsbrain.image" -}}
{{- $tag := .svc.tag | default .root.Values.image.tag -}}
{{- printf "%s/%s:%s" .root.Values.image.registry .svc.image $tag -}}
{{- end -}}

{{/*
Secret-backed environment per service. Optional keys use `optional: true` so a
missing token degrades that feature instead of blocking the pod from starting.
*/}}
{{- define "opsbrain.secretEnv" -}}
{{- $s := .root.Values.secrets -}}
{{- $refs := dict
    "orchestrator" (list (list "LLM_API_KEY" $s.keys.llmApiKey false))
    "rag-agent" (list (list "LLM_API_KEY" $s.keys.llmApiKey false) (list "GOOGLE_API_KEY" $s.keys.googleApiKey false) (list "DATABASE_URL" $s.keys.databaseUrl false))
    "monitoring-agent" (list (list "GRAFANA_API_TOKEN" $s.keys.grafanaApiToken true))
    "code-agent" (list (list "GITHUB_TOKEN" $s.keys.githubToken true))
-}}
{{- range (get $refs .name | default list) }}
- name: {{ index . 0 }}
  valueFrom:
    secretKeyRef:
      name: {{ $s.name }}
      key: {{ index . 1 }}
      {{- if index . 2 }}
      optional: true
      {{- end }}
{{- end }}
{{- end -}}
