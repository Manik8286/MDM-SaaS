#!/bin/bash
set -e
CERT_DIR="./certs/dev"
mkdir -p "$CERT_DIR"

echo "Generating dev CA..."
openssl genrsa -out "$CERT_DIR/ca.key" 4096
openssl req -new -x509 -days 3650 -key "$CERT_DIR/ca.key" \
  -out "$CERT_DIR/ca.pem" \
  -subj "/C=IN/O=MDM SaaS Dev CA/CN=MDM Dev Root CA"

echo "Generating MDM signing cert..."
openssl genrsa -out "$CERT_DIR/mdm_signing.key" 2048
openssl req -new -key "$CERT_DIR/mdm_signing.key" \
  -out "$CERT_DIR/mdm_signing.csr" \
  -subj "/C=IN/O=MDM SaaS/CN=MDM Profile Signing"
openssl x509 -req -days 365 \
  -in "$CERT_DIR/mdm_signing.csr" \
  -CA "$CERT_DIR/ca.pem" -CAkey "$CERT_DIR/ca.key" \
  -CAcreateserial -out "$CERT_DIR/mdm_signing.pem"

echo "Generating test device identity cert..."
openssl genrsa -out "$CERT_DIR/device_identity.key" 2048
openssl req -new -key "$CERT_DIR/device_identity.key" \
  -out "$CERT_DIR/device_identity.csr" \
  -subj "/C=IN/O=MDM SaaS/CN=Test Device/UID=AAAA-BBBB-CCCC-DDDD"
openssl x509 -req -days 365 \
  -in "$CERT_DIR/device_identity.csr" \
  -CA "$CERT_DIR/ca.pem" -CAkey "$CERT_DIR/ca.key" \
  -CAcreateserial -out "$CERT_DIR/device_identity.pem"

echo "Done. Install ca.pem on test Mac:"
echo "  sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain $CERT_DIR/ca.pem"
