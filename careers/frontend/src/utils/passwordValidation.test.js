import { describe, it, expect } from 'vitest';
import { getPasswordValidationState, isPasswordValid, getPasswordStrength } from './passwordValidation';

describe('passwordValidation', () => {
  describe('getPasswordValidationState', () => {
    it('returns true for all conditions on a valid password', () => {
      const state = getPasswordValidationState('StrongP@ssw0rd');
      expect(state.length).toBe(true);
      expect(state.uppercase).toBe(true);
      expect(state.lowercase).toBe(true);
      expect(state.number).toBe(true);
      expect(state.specialChar).toBe(true);
      expect(state.noSpaces).toBe(true);
      expect(state.notCommon).toBe(true);
    });

    it('detects common passwords', () => {
      const state = getPasswordValidationState('password123');
      expect(state.notCommon).toBe(false);
    });
  });

  describe('isPasswordValid', () => {
    it('returns false for weak passwords', () => {
      expect(isPasswordValid('weak')).toBe(false);
      expect(isPasswordValid('password')).toBe(false);
      expect(isPasswordValid('Password123')).toBe(false); // No special char
    });

    it('returns true for strong passwords', () => {
      expect(isPasswordValid('StrongP@ssw0rd!')).toBe(true);
    });
  });

  describe('getPasswordStrength', () => {
    it('returns Weak for short or simple passwords', () => {
      expect(getPasswordStrength('weak')).toBe('Weak');
      expect(getPasswordStrength('Password')).toBe('Weak');
    });

    it('returns Medium for moderate passwords', () => {
      expect(getPasswordStrength('StrongP@ss')).toBe('Medium');
    });

    it('returns Strong for long complex passwords', () => {
      expect(getPasswordStrength('VeryStrongP@ssw0rd!')).toBe('Strong');
    });
  });
});
