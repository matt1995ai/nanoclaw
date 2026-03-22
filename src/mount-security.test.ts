import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock pino before importing the module under test
vi.mock('pino', () => {
  const logger = {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    child: vi.fn(() => logger),
  };
  return { default: vi.fn(() => logger) };
});

// Mock config to provide a predictable allowlist path
vi.mock('./config.js', () => ({
  MOUNT_ALLOWLIST_PATH: '/tmp/test-mount-allowlist.json',
}));

// Mock fs for allowlist loading and path resolution
const mockReadFileSync = vi.fn();
const mockExistsSync = vi.fn();
const mockRealpathSync = vi.fn();
vi.mock('fs', async () => {
  const actual = await vi.importActual<typeof import('fs')>('fs');
  return {
    ...actual,
    default: {
      ...actual,
      readFileSync: (...args: unknown[]) => mockReadFileSync(...args),
      existsSync: (...args: unknown[]) => mockExistsSync(...args),
      realpathSync: {
        native: (...args: unknown[]) => mockRealpathSync(...args),
      },
    },
    readFileSync: (...args: unknown[]) => mockReadFileSync(...args),
    existsSync: (...args: unknown[]) => mockExistsSync(...args),
  };
});

import { applyMountOverrides, validateMount } from './mount-security.js';
import type { AdditionalMount, MountOverride } from './types.js';

// Helper to create validated mount arrays (simulating validateAdditionalMounts output)
function makeValidated(
  entries: Array<{ name: string; hostPath: string; readonly: boolean }>,
) {
  return entries.map((e) => ({
    hostPath: e.hostPath,
    containerPath: `/workspace/extra/${e.name}`,
    readonly: e.readonly,
  }));
}

describe('applyMountOverrides', () => {
  it('restricts rw mount to ro', () => {
    const base = makeValidated([
      { name: 'vault', hostPath: '/home/user/vault', readonly: false },
      { name: 'dev', hostPath: '/home/user/dev', readonly: false },
    ]);
    const raw: AdditionalMount[] = [
      { hostPath: '/home/user/vault', containerPath: 'vault', readonly: false },
      { hostPath: '/home/user/dev', containerPath: 'dev', readonly: false },
    ];
    const overrides: MountOverride[] = [{ path: 'dev', mode: 'ro' }];

    const result = applyMountOverrides(base, raw, overrides, true);

    expect(result[0].readonly).toBe(false); // vault unchanged
    expect(result[1].readonly).toBe(true); // dev restricted
  });

  it('respects floor protection — cannot restrict floor mount', () => {
    const base = makeValidated([
      { name: 'vault', hostPath: '/home/user/vault', readonly: false },
      { name: 'dev', hostPath: '/home/user/dev', readonly: false },
    ]);
    const raw: AdditionalMount[] = [
      {
        hostPath: '/home/user/vault',
        containerPath: 'vault',
        readonly: false,
        floor: true,
      },
      { hostPath: '/home/user/dev', containerPath: 'dev', readonly: false },
    ];
    const overrides: MountOverride[] = [{ path: 'vault', mode: 'ro' }];

    const result = applyMountOverrides(base, raw, overrides, true);

    expect(result[0].readonly).toBe(false); // vault stays rw (floor)
  });

  it('skips override for non-existent mount path', () => {
    const base = makeValidated([
      { name: 'vault', hostPath: '/home/user/vault', readonly: false },
    ]);
    const raw: AdditionalMount[] = [
      { hostPath: '/home/user/vault', containerPath: 'vault', readonly: false },
    ];
    const overrides: MountOverride[] = [
      { path: 'nonexistent', mode: 'ro' },
    ];

    const result = applyMountOverrides(base, raw, overrides, true);

    expect(result).toHaveLength(1);
    expect(result[0].readonly).toBe(false); // vault unchanged
  });

  it('returns base mounts unchanged when overrides array is empty', () => {
    const base = makeValidated([
      { name: 'vault', hostPath: '/home/user/vault', readonly: false },
      { name: 'dev', hostPath: '/home/user/dev', readonly: false },
    ]);
    const raw: AdditionalMount[] = [
      { hostPath: '/home/user/vault', containerPath: 'vault', readonly: false },
      { hostPath: '/home/user/dev', containerPath: 'dev', readonly: false },
    ];

    const result = applyMountOverrides(base, raw, [], true);

    expect(result[0].readonly).toBe(false);
    expect(result[1].readonly).toBe(false);
  });

  it('normalizes full container path in override', () => {
    const base = makeValidated([
      { name: 'dev', hostPath: '/home/user/dev', readonly: false },
    ]);
    const raw: AdditionalMount[] = [
      { hostPath: '/home/user/dev', containerPath: 'dev', readonly: false },
    ];
    const overrides: MountOverride[] = [
      { path: '/workspace/extra/dev', mode: 'ro' },
    ];

    const result = applyMountOverrides(base, raw, overrides, true);

    expect(result[0].readonly).toBe(true); // matched by full path
  });

  it('does not mutate original base mounts array', () => {
    const base = makeValidated([
      { name: 'dev', hostPath: '/home/user/dev', readonly: false },
    ]);
    const raw: AdditionalMount[] = [
      { hostPath: '/home/user/dev', containerPath: 'dev', readonly: false },
    ];
    const overrides: MountOverride[] = [{ path: 'dev', mode: 'ro' }];

    applyMountOverrides(base, raw, overrides, true);

    expect(base[0].readonly).toBe(false); // original unchanged
  });

  it('no-ops when override mode matches current state', () => {
    const base = makeValidated([
      { name: 'dev', hostPath: '/home/user/dev', readonly: true },
    ]);
    const raw: AdditionalMount[] = [
      { hostPath: '/home/user/dev', containerPath: 'dev', readonly: true },
    ];
    const overrides: MountOverride[] = [{ path: 'dev', mode: 'ro' }];

    const result = applyMountOverrides(base, raw, overrides, true);

    expect(result[0].readonly).toBe(true); // stays ro
  });
});
