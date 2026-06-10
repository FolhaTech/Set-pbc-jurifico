import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { execSync } from 'child_process';

function getMachineId() {
  try {
    let output = execSync('REG QUERY HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography /v MachineGuid', { encoding: 'utf8' });
    let match = output.match(/MachineGuid\s+REG_SZ\s+(\S+)/i);
    if (match) {
      return match[1].trim().toLowerCase();
    }
  } catch (e) {
    console.error("Error getting registry MachineGuid:", e);
  }
  return null;
}

const machineId = getMachineId();
if (!machineId) {
  console.log(JSON.stringify({ success: false, error: "Could not get machine ID" }));
  process.exit(1);
}

const SALT_V2 = "adapta-agent-desktop-auth-v2";
const encryptionKey = crypto.pbkdf2Sync(
  machineId,
  SALT_V2,
  100000,
  32,
  "sha256"
);

function decryptWithKey(ciphertextBase64, key) {
  const combined = Buffer.from(ciphertextBase64, "base64");
  const iv = combined.subarray(0, 12);
  const authTag = combined.subarray(12, 28);
  const encrypted = combined.subarray(28);
  const decipher = crypto.createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(authTag);
  let decrypted = decipher.update(encrypted, undefined, "utf8");
  decrypted += decipher.final("utf8");
  return decrypted;
}

const appData = process.env.APPDATA || path.join(process.env.USERPROFILE, 'AppData', 'Roaming');
const storageFile = path.join(appData, 'AdaptaONE', 'auth-session.enc');

if (!fs.existsSync(storageFile)) {
  console.log(JSON.stringify({ success: false, error: `File not found: ${storageFile}` }));
  process.exit(1);
}

try {
  const encryptedData = fs.readFileSync(storageFile, "utf-8");
  const decrypted = decryptWithKey(encryptedData, encryptionKey);
  const data = JSON.parse(decrypted);
  console.log(JSON.stringify({ success: true, token: data.accessToken, user: data.user }));
} catch (error) {
  console.log(JSON.stringify({ success: false, error: error.message }));
}
