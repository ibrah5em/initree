# Secrets to provision

initree generated this from the secrets your recipes reference. Each entry is a logical
purpose, not a value — set it in your CI/CD provider's secret store before the first
pipeline run. The ci layer resolves each purpose to its native variable; the values
themselves never live in the generated project.

## Masked variables

- `registry` — registry password/token (push)
- `registry_user` — registry username (push)
