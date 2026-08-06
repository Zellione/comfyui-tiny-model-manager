// @ts-check
const eslint = require('@eslint/js');
const tseslint = require('typescript-eslint');
// angular-eslint 22 moved the shareable configs from the individual plugin
// packages into this meta-package; the plugins now export only their rules.
const angular = require('angular-eslint');

module.exports = tseslint.config(
  {
    files: ['**/*.ts'],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.recommended,
      ...angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      // Constructor injection is the existing pattern — migrate separately via
      // `ng generate @angular/core:inject` when desired.
      '@angular-eslint/prefer-inject': 'off',
    },
  },
  {
    files: ['**/*.html'],
    extends: [...angular.configs.templateRecommended],
    rules: {},
  },
);
