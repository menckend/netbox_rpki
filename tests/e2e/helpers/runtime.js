const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '../../..');
const AUTH_STATE_FILE = path.join(REPO_ROOT, 'tests/e2e/.auth/admin.json');
const RUNTIME_STATE_FILE = path.join(REPO_ROOT, 'tests/e2e/.state/runtime.json');
const PREPARE_SCRIPT_FILE = path.join(REPO_ROOT, 'tests/e2e/scripts/prepare_netbox_rpki_e2e.py');
const FIXTURE_PREFIX = 'NETBOX_RPKI_E2E_FIXTURES=';

function resolvePath(value) {
  if (!value) {
    return value;
  }
  if (value === '~') {
    return os.homedir();
  }
  if (value.startsWith('~/')) {
    return path.join(os.homedir(), value.slice(2));
  }
  return value;
}

function ensureParentDir(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function parseEnvFile(filePath) {
  if (!filePath || !fs.existsSync(filePath)) {
    return {};
  }

  const values = {};
  for (const rawLine of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) {
      continue;
    }

    const separatorIndex = line.indexOf('=');
    const key = line.slice(0, separatorIndex).trim();
    let value = line.slice(separatorIndex + 1).trim();

    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }

  return values;
}

function resolveE2eConfig() {
  const release = process.env.NETBOX_E2E_NETBOX_RELEASE || '4.5.7';
  const credentialsFile = resolvePath(
    process.env.NETBOX_E2E_CREDENTIALS_FILE || '~/.config/netbox-rpki-dev/credentials.env'
  );
  const credentials = parseEnvFile(credentialsFile);
  const netboxProjectDir = resolvePath(
    process.env.NETBOX_E2E_NETBOX_PROJECT_DIR || `~/src/netbox-v${release}/netbox`
  );
  const venvDir = resolvePath(process.env.NETBOX_E2E_VENV_DIR || `~/.virtualenvs/netbox-${release}`);
  const defaultPython = path.join(venvDir, 'bin', 'python');
  const pythonExecutable = resolvePath(
    process.env.NETBOX_E2E_PYTHON || (fs.existsSync(defaultPython) ? defaultPython : 'python3')
  );
  const username = process.env.NETBOX_E2E_USERNAME || 'admin';
  const password = process.env.NETBOX_E2E_PASSWORD || credentials.NETBOX_ADMIN_PASSWORD;

  if (!password) {
    throw new Error(
      `Unable to resolve the NetBox admin password. Set NETBOX_E2E_PASSWORD or provide ${credentialsFile}.`
    );
  }

  return {
    baseURL: process.env.NETBOX_E2E_BASE_URL || 'http://127.0.0.1:8000',
    credentialsFile,
    netboxProjectDir,
    password,
    pythonExecutable,
    release,
    username,
  };
}

function prepareRuntimeState() {
  const config = resolveE2eConfig();
  const script = fs.readFileSync(PREPARE_SCRIPT_FILE, 'utf8');

  const stdout = execFileSync(config.pythonExecutable, ['manage.py', 'shell'], {
    cwd: config.netboxProjectDir,
    env: {
      ...process.env,
      NETBOX_RPKI_ENABLE: '1',
    },
    encoding: 'utf8',
    input: script,
  });

  const fixtureLine = stdout
    .trim()
    .split(/\r?\n/)
    .reverse()
    .find((line) => line.startsWith(FIXTURE_PREFIX));

  if (!fixtureLine) {
    throw new Error(`Failed to parse fixture output from manage.py shell. Output was:\n${stdout}`);
  }

  const fixtures = JSON.parse(fixtureLine.slice(FIXTURE_PREFIX.length));
  const runtimeState = {
    baseURL: config.baseURL,
    fixtures,
    netboxProjectDir: config.netboxProjectDir,
    pythonExecutable: config.pythonExecutable,
    username: config.username,
  };

  ensureParentDir(RUNTIME_STATE_FILE);
  fs.writeFileSync(RUNTIME_STATE_FILE, `${JSON.stringify(runtimeState, null, 2)}\n`);

  return {
    ...config,
    fixtures,
  };
}

function readRuntimeState() {
  if (!fs.existsSync(RUNTIME_STATE_FILE)) {
    throw new Error(`Runtime state file is missing: ${RUNTIME_STATE_FILE}`);
  }

  return JSON.parse(fs.readFileSync(RUNTIME_STATE_FILE, 'utf8'));
}

module.exports = {
  AUTH_STATE_FILE,
  PREPARE_SCRIPT_FILE,
  RUNTIME_STATE_FILE,
  prepareRuntimeState,
  readRuntimeState,
  resolveE2eConfig,
};