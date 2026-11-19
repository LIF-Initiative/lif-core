FROM dagster/dagster-cloud-agent:1.11.4
# Distrust the eMudhra emSign roots C1, C3 and G3, which certifi 2026.10.23 no longer carries, and
# Sectigo's Comodo AAA Services root, which cross-signs the compromised emSign intermediates (#1480).
# Debian's ca-certificates may still ship them. The grep fails the build if one is still trusted
# under a name the sed doesn't match.
RUN sed -i -E 's@^(mozilla/(emSign_(Root_CA_-_C1|ECC_Root_CA_-_C3|ECC_Root_CA_-_G3)|Comodo_AAA_Services_root)\.crt)$@!\1@' /etc/ca-certificates.conf \
    && ! grep -iqE '^mozilla/.*(emsign.*(c1|c3|g3)|aaa.?services)' /etc/ca-certificates.conf \
    && update-ca-certificates --fresh > /dev/null
# The agent image's own certifi predates the fix, and no lock file covers it; pin the release the
# lock files use (#1480).
RUN pip install --no-cache-dir 'certifi==2026.10.23'

COPY entrypoint.sh /

CMD ["/entrypoint.sh"]
