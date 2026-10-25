#!/bin/sh
# Production's Alertmanager starts here (docker-compose.prod.yml). The Discord webhook and the SMTP
# password from .env.prod go to the files alertmanager.yml reads, the two addresses go over its
# placeholders in a copy on /tmp, and the command runs without the four in its environment.
# Nothing here prints a value.
set -eu

for name in ALERT_DISCORD_WEBHOOK_URL ALERT_SMTP_PASSWORD ALERT_EMAIL_FROM ALERT_EMAIL_TO; do
  eval "value=\${$name:-}"
  if [ -z "$value" ]; then
    echo "$name is empty: set it in .env.prod (docs/deploy.md, Alert delivery)" >&2
    exit 1
  fi
done
# The addresses go into the config as written, so only an address's own characters pass: one
# sender, and recipients as a comma-separated list.
case "$ALERT_EMAIL_FROM" in
  *[!A-Za-z0-9.@+_-]*)
    echo "ALERT_EMAIL_FROM takes one address: letters, digits and . @ + _ - only" >&2
    exit 1
    ;;
esac
case "$ALERT_EMAIL_TO" in
  *[!A-Za-z0-9.@+_,-]*)
    echo "ALERT_EMAIL_TO takes addresses: letters, digits and . @ + _ - , only" >&2
    exit 1
    ;;
esac

umask 077
printf '%s' "$ALERT_DISCORD_WEBHOOK_URL" > /tmp/discord-webhook-url
printf '%s' "$ALERT_SMTP_PASSWORD" > /tmp/smtp-password
sed -e "s/ALERT_EMAIL_FROM/$ALERT_EMAIL_FROM/g" -e "s/ALERT_EMAIL_TO/$ALERT_EMAIL_TO/g" \
  /etc/alertmanager/alertmanager.yml > /tmp/alertmanager.yml
unset value ALERT_DISCORD_WEBHOOK_URL ALERT_SMTP_PASSWORD ALERT_EMAIL_FROM ALERT_EMAIL_TO
exec "$@"
