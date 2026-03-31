"""
Windows MDM Enrollment Server — MS-MDE2 protocol.

Three SOAP endpoints required for Windows MDM enrollment:
  GET/POST /EnrollmentServer/Discovery.svc  — device finds enrollment URLs
  POST     /EnrollmentServer/Policy.svc     — server declares auth policy
  POST     /EnrollmentServer/Enrollment.svc — WSTEP: server issues device cert

After enrollment, Windows checks in via OMA-DM at:
  POST /ManagementServer/MDM.svc

Enrollment flow on Windows:
  Settings → Accounts → Access work or school →
  Enroll only in device management → enter server URL → credentials

References:
  MS-MDE2: https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-mde2/
"""
import base64
import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import get_db
from app.db.models import Device, Tenant, User

from .ca import sign_device_csr, cert_thumbprint

log = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

_WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
_WSA_NS = "http://www.w3.org/2005/08/addressing"


def _soap_msg_id(body: bytes) -> str:
    try:
        root = ET.fromstring(body)
        el = root.find(f".//{{{_WSA_NS}}}MessageID")
        if el is not None and el.text:
            return el.text.strip()
    except Exception:
        pass
    return f"urn:uuid:{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# 1. Discovery
# ---------------------------------------------------------------------------

@router.get("/EnrollmentServer/Discovery.svc")
async def discovery_get():
    """Device probes this URL to discover enrollment endpoints."""
    base = settings.mdm_server_url.rstrip("/")
    return {
        "AuthPolicy": "OnPremise",
        "EnrollmentVersion": "4.0",
        "EnrollmentPolicyServiceUrl": f"{base}/EnrollmentServer/Policy.svc",
        "EnrollmentServiceUrl": f"{base}/EnrollmentServer/Enrollment.svc",
        "AuthenticationServiceUrl": None,
    }


@router.post("/EnrollmentServer/Discovery.svc")
async def discovery_post(request: Request):
    """Some Windows versions POST a SOAP discovery request."""
    body = await request.body()
    msg_id = _soap_msg_id(body)
    base = settings.mdm_server_url.rstrip("/")
    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:a="http://www.w3.org/2005/08/addressing">
  <s:Header>
    <a:Action s:mustUnderstand="1">
      http://schemas.microsoft.com/windows/management/2012/01/enrollment/IDiscoveryService/DiscoverResponse
    </a:Action>
    <a:RelatesTo>{msg_id}</a:RelatesTo>
  </s:Header>
  <s:Body>
    <DiscoverResponse xmlns="http://schemas.microsoft.com/windows/management/2012/01/enrollment">
      <DiscoverResult>
        <AuthPolicy>OnPremise</AuthPolicy>
        <EnrollmentVersion>4.0</EnrollmentVersion>
        <EnrollmentPolicyServiceUrl>{base}/EnrollmentServer/Policy.svc</EnrollmentPolicyServiceUrl>
        <EnrollmentServiceUrl>{base}/EnrollmentServer/Enrollment.svc</EnrollmentServiceUrl>
      </DiscoverResult>
    </DiscoverResponse>
  </s:Body>
</s:Envelope>"""
    return Response(content=soap, media_type="application/soap+xml; charset=utf-8")


# ---------------------------------------------------------------------------
# 2. Policy
# ---------------------------------------------------------------------------

@router.post("/EnrollmentServer/Policy.svc")
async def policy(request: Request):
    """Return certificate enrollment policy — OnPremise auth, 2048-bit RSA."""
    body = await request.body()
    msg_id = _soap_msg_id(body)
    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:a="http://www.w3.org/2005/08/addressing">
  <s:Header>
    <a:Action s:mustUnderstand="1">
      http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy/IPolicy/GetPoliciesResponse
    </a:Action>
    <a:RelatesTo>{msg_id}</a:RelatesTo>
  </s:Header>
  <s:Body>
    <GetPoliciesResponse xmlns="http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy">
      <response>
        <policyID/>
        <policyFriendlyName/>
        <nextUpdateHours xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
        <policiesNotChanged xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
        <policies>
          <policy>
            <policyOIDReference>0</policyOIDReference>
            <cAs xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
            <attributes>
              <commonName>MDMEnroll</commonName>
              <policySchema>3</policySchema>
              <certificateValidity>
                <validityPeriodSeconds>31536000</validityPeriodSeconds>
                <renewalPeriodSeconds>7776000</renewalPeriodSeconds>
              </certificateValidity>
              <permission>
                <enroll>true</enroll>
                <autoEnroll>false</autoEnroll>
              </permission>
              <privateKeyAttributes>
                <minimalKeyLength>2048</minimalKeyLength>
                <keySpec xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
                <keyUsageProperty xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
                <permissions xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
                <algorithmOIDReference xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
                <cryptoProviders xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
              </privateKeyAttributes>
              <revision>
                <majorRevision>101</majorRevision>
                <minorRevision>0</minorRevision>
              </revision>
              <supersededPolicies xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
              <privateKeyFlags xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
              <subjectNameFlags xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
              <enrollmentFlags xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
              <generalFlags xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
              <hashAlgorithmOIDReference>0</hashAlgorithmOIDReference>
              <rARequirements xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
              <keyArchivalAttributes xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
              <extensions xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
            </attributes>
          </policy>
        </policies>
      </response>
      <cAs xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
      <oIDs>
        <oID>
          <value>1.3.14.3.2.29</value>
          <group>1</group>
          <oIDReferenceID>0</oIDReferenceID>
          <defaultName>szOID_OIWSEC_sha1RSASign</defaultName>
        </oID>
      </oIDs>
    </GetPoliciesResponse>
  </s:Body>
</s:Envelope>"""
    return Response(content=soap, media_type="application/soap+xml; charset=utf-8")


# ---------------------------------------------------------------------------
# 3. Enrollment (WSTEP)
# ---------------------------------------------------------------------------

def _provisioning_doc(device_cert_b64: str, ca_cert_b64: str,
                      device_thumbprint: str, ca_thumbprint: str, mgmt_url: str) -> str:
    """
    WAP Provisioning XML returned inside the WSTEP RSTR.
    Tells Windows: which cert to use for mTLS, which server to check in to,
    and the polling schedule.
    Certificate characteristic types must be the SHA1 thumbprint of the cert.
    """
    return f"""<wap-provisioningdoc version="1.1">
  <characteristic type="CertificateStore">
    <characteristic type="Root">
      <characteristic type="System">
        <characteristic type="{ca_thumbprint}">
          <parm name="EncodedCertificate" value="{ca_cert_b64}"/>
        </characteristic>
      </characteristic>
    </characteristic>
    <characteristic type="My">
      <characteristic type="User">
        <characteristic type="{device_thumbprint}">
          <parm name="EncodedCertificate" value="{device_cert_b64}"/>
        </characteristic>
      </characteristic>
    </characteristic>
  </characteristic>
  <characteristic type="APPLICATION">
    <parm name="APPID" value="w7"/>
    <parm name="PROVIDER-ID" value="MDMSaaS"/>
    <parm name="NAME" value="MDM SaaS"/>
    <parm name="ADDR" value="{mgmt_url}"/>
    <parm name="DEFAULTENCODING" value="application/vnd.syncml.dm+xml"/>
    <parm name="SSLCLIENTCERTSEARCHCRITERIA"
          value="Thumbprint={device_thumbprint}&amp;Stores=MY%5CUser"/>
  </characteristic>
</wap-provisioningdoc>"""


@router.post("/EnrollmentServer/Enrollment.svc")
async def enrollment_wstep(request: Request, db: AsyncSession = Depends(get_db)):
    """
    WSTEP endpoint — device sends a PKCS#10 CSR in a WS-Trust RST.
    Server signs it with the dev CA and returns a WAP provisioning document.
    """
    body = await request.body()
    msg_id = _soap_msg_id(body)
    device_id = str(uuid.uuid4())
    username = None
    csr_b64 = None

    try:
        root = ET.fromstring(body)
        user_el = root.find(f".//{{{_WSSE_NS}}}Username")
        if user_el is not None and user_el.text:
            username = user_el.text.strip()
        bst_el = root.find(f".//{{{_WSSE_NS}}}BinarySecurityToken")
        if bst_el is not None and bst_el.text:
            csr_b64 = bst_el.text.strip()
    except ET.ParseError as e:
        log.warning("WSTEP SOAP parse error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid SOAP body")

    if not csr_b64:
        raise HTTPException(status_code=400, detail="Missing CSR in enrollment request")

    try:
        csr_der = base64.b64decode(csr_b64)
        device_cert_der, ca_cert_der = sign_device_csr(csr_der, device_id)
    except Exception:
        log.exception("CSR signing failed")
        raise HTTPException(status_code=500, detail="Certificate issuance failed")

    tenant_id = await _resolve_tenant(username, db)
    if tenant_id:
        device = Device(
            id=device_id,
            tenant_id=tenant_id,
            udid=device_id,
            platform="windows",
            status="enrolled",
            enrolled_at=datetime.utcnow(),
            last_checkin=datetime.utcnow(),
        )
        db.add(device)
        log.info("Windows device enrolled: id=%s tenant=%s user=%s", device_id, tenant_id, username)
    else:
        log.warning("WSTEP: could not resolve tenant for user=%s", username)

    device_cert_b64 = base64.b64encode(device_cert_der).decode()
    ca_cert_b64 = base64.b64encode(ca_cert_der).decode()
    device_thumbprint = cert_thumbprint(device_cert_der)
    ca_thumbprint = cert_thumbprint(ca_cert_der)
    base_url = settings.mdm_server_url.rstrip("/")
    prov_xml = _provisioning_doc(device_cert_b64, ca_cert_b64, device_thumbprint, ca_thumbprint, f"{base_url}/ManagementServer/MDM.svc")
    prov_b64 = base64.b64encode(prov_xml.encode()).decode()

    now = datetime.utcnow()
    created = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    expires = now.replace(year=now.year + 1).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:a="http://www.w3.org/2005/08/addressing"
            xmlns:u="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
  <s:Header>
    <a:Action s:mustUnderstand="1">
      http://schemas.microsoft.com/windows/pki/2009/01/enrollment/RSTRC/wstep
    </a:Action>
    <a:RelatesTo>{msg_id}</a:RelatesTo>
    <o:Security xmlns:o="{_WSSE_NS}">
      <u:Timestamp>
        <u:Created>{created}</u:Created>
        <u:Expires>{expires}</u:Expires>
      </u:Timestamp>
    </o:Security>
  </s:Header>
  <s:Body>
    <RequestSecurityTokenResponseCollection
        xmlns="http://docs.oasis-open.org/ws-sx/ws-trust/200512">
      <RequestSecurityTokenResponse>
        <TokenType>http://schemas.microsoft.com/5.0.0.0/ConfigurationManager/Enrollment/DeviceEnrollmentToken</TokenType>
        <RequestedSecurityToken>
          <BinarySecurityToken
              ValueType="http://schemas.microsoft.com/5.0.0.0/ConfigurationManager/Enrollment/DeviceEnrollmentProvisioningDoc"
              EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd#base64binary"
              xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">{prov_b64}</BinarySecurityToken>
        </RequestedSecurityToken>
        <RequestSecurityTokenResponse/>
      </RequestSecurityTokenResponse>
    </RequestSecurityTokenResponseCollection>
  </s:Body>
</s:Envelope>"""
    return Response(content=soap, media_type="application/soap+xml; charset=utf-8")


async def _resolve_tenant(username: str | None, db: AsyncSession) -> str | None:
    if username:
        result = await db.execute(select(User).where(User.email == username).limit(1))
        user = result.scalar_one_or_none()
        if user:
            return user.tenant_id
    result = await db.execute(select(Tenant).limit(1))
    tenant = result.scalar_one_or_none()
    return tenant.id if tenant else None
