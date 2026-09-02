# GigaChat CA certificates

The certificates in this directory are the official Russian Trusted Root CA
and Russian Trusted Sub CA required by GigaChat.

Sources:

- https://developers.sber.ru/docs/ru/gigachat/certificates?OS=debian-ubuntu
- https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt
- https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt

They are installed into the Debian trust store by `backend/Dockerfile`. TLS
verification must remain enabled.
