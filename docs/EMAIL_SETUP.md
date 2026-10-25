# Email setup (SMTP, Amazon SES, DKIM/SPF/DMARC)

`MAIL_PROVIDER` = `sandbox` (default, records the email, sends nothing) | `smtp` | `ses`. Code: `services/mailer.py` (providers) and `services/mail_transport.py` (SMTP). Verified against a fake SMTP server in tests only: send one real test mail to yourself before launch.

## SMTP (cPanel mail, Zoho, Brevo, Mailgun SMTP ...)
```
MAIL_PROVIDER=smtp
MAIL_SMTP_HOST=mail.example.com
MAIL_SMTP_PORT=587
MAIL_SMTP_SECURITY=starttls        # starttls | ssl (port 465) | none
MAIL_SMTP_USER=hello@example.com
MAIL_SMTP_PASSWORD=...             # secret
MAIL_FROM=FlatWise <hello@example.com>
MAIL_REPLY_TO=support@example.com  # optional
MAIL_SMTP_TIMEOUT=15  MAIL_SMTP_RETRIES=2
```
Temporary failures (connection errors, 4xx) are retried with backoff; permanent ones (5xx, refused recipient, bad login) fail at once and the outbox row shows `failed` with the reason. Every message carries `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`. cPanel shared mail usually limits to a few hundred mails an hour: set the campaign throttle (Mail settings, `throttle_per_hour`) below that, or use a transactional provider.

## Amazon SES
SES is used through its **SMTP interface** (no boto3).
```
MAIL_PROVIDER=ses
SES_REGION=ap-southeast-1                 # host becomes email-smtp.<region>.amazonaws.com
MAIL_SMTP_USER=<SES SMTP username>        # created in the SES console > SMTP settings (NOT your AWS access key)
MAIL_SMTP_PASSWORD=<SES SMTP password>
MAIL_FROM=FlatWise <hello@example.com>    # a verified identity
SES_CONFIGURATION_SET=flatwise-events     # optional, adds X-SES-CONFIGURATION-SET
SES_SNS_TOPIC_ARN=arn:aws:sns:...         # recommended: only accept this topic
```
Steps: verify the domain in SES (Easy DKIM, below), request production access (leave the sandbox), create an SNS topic, create a configuration set with an event destination (Bounce, Complaint, Delivery) to that topic, and subscribe `https://<your-site>/api/webhooks/ses` over HTTPS. The endpoint confirms the subscription by itself.

### Bounces and complaints
`POST /api/webhooks/ses` accepts SNS messages. It **verifies the SNS signature** (certificate must come from `sns.<region>.amazonaws.com`, SignatureVersion 1 and 2) unless `SES_WEBHOOK_VERIFY=0` (never in production). Effects:
* Permanent bounce: address goes on the suppression list (`bounce`, blocks all mail including transactional), the latest outbox row becomes `bounced`.
* Transient bounce: ignored (mailbox full is not a reason to stop).
* Complaint: suppression `complaint`.
* Delivery: `delivered_at` is set on the latest outbox row.
Both the classic `notificationType` and the configuration-set `eventType` formats are read.

## DNS: SPF, DKIM, DMARC
Do this for the domain in `MAIL_FROM`; without it mail goes to spam.

**SPF** (one TXT record at the domain; merge, never create two):
* SES: `v=spf1 include:amazonses.com ~all`
* cPanel host: `v=spf1 +a +mx include:<host's spf include> ~all` (cPanel > Email Deliverability shows the exact record)
* Both: `v=spf1 include:amazonses.com +a +mx ~all`

**DKIM**: SES > Verified identities > your domain > Easy DKIM gives three CNAME records (`xxxx._domainkey.example.com` -> `xxxx.dkim.amazonses.com`). Add all three; status turns *Verified* within minutes to 72 h. For SMTP through cPanel, cPanel > Email Deliverability > Manage > Install the suggested DKIM record.

**DMARC** (TXT at `_dmarc.example.com`): start with monitoring
`v=DMARC1; p=none; rua=mailto:dmarc@example.com; adkim=s; aspf=s`
After a few weeks of clean reports move to `p=quarantine`, later `p=reject`.

**Also**: set a custom MAIL FROM domain in SES (so SPF aligns), a reverse DNS (PTR) on your own server if you send directly, and test with mail-tester.com or Gmail "Show original" (SPF/DKIM/DMARC must all say PASS).

## Credits
SMS and email credit use are separate (`messaging.deliver`); SaaS own mail (campaigns, trial and dunning mails) does not use customer credits.
