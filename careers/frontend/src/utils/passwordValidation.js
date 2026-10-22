export const COMMON_WEAK_PASSWORDS = new Set([
  "password", "12345678", "123456789", "qwerty", "1234567890",
  "password123", "admin123", "iloveyou", "password1234"
]);

export function getPasswordValidationState(password) {
  return {
    length: password.length >= 8 && password.length <= 64,
    uppercase: /[A-Z]/.test(password),
    lowercase: /[a-z]/.test(password),
    number: /\d/.test(password),
    specialChar: /[^A-Za-z0-9]/.test(password),
    noSpaces: !password.includes(" "),
    notCommon: !COMMON_WEAK_PASSWORDS.has(password.toLowerCase()),
  };
}

export function isPasswordValid(password) {
  if (!password) return false;
  const state = getPasswordValidationState(password);
  return Object.values(state).every(Boolean);
}

export function getPasswordStrength(password) {
  if (!password) return "None";

  const state = getPasswordValidationState(password);

  // Calculate score based on met conditions (excluding noSpaces and notCommon for raw strength)
  const conditionsMet = [
    state.length,
    state.uppercase,
    state.lowercase,
    state.number,
    state.specialChar
  ].filter(Boolean).length;

  if (!state.notCommon || conditionsMet < 3 || password.length < 8) return "Weak";
  if (conditionsMet === 5 && password.length >= 12 && state.noSpaces && state.notCommon) return "Strong";
  return "Medium";
}
