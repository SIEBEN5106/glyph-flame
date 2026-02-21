/**
 * Custom Error Classes for Theme System
 *
 * Hierarchical error classes for different failure scenarios.
 */

/**
 * Base Theme Error class
 */
export class ThemeError extends Error {
	constructor(message: string) {
		super(message);
		this.name = 'ThemeError';
		Object.setPrototypeOf(this, ThemeError.prototype);
	}

	/** User-friendly error message */
	getUserMessage(): string {
		return this.message;
	}

	/** Error code for programmatic handling */
	getErrorCode(): string {
		return 'THEME_ERROR';
	}
}

/**
 * Unsupported version error - firmware version doesn't support themes
 */
export class UnsupportedVersionError extends ThemeError {
	constructor(version: string, message?: string) {
		super(message ?? `Firmware version ${version} does not support theme system`);
		this.name = 'UnsupportedVersionError';
		Object.setPrototypeOf(this, UnsupportedVersionError.prototype);
	}

	getErrorCode(): string {
		return 'UNSUPPORTED_VERSION';
	}
}

/**
 * Already patched error - firmware is already patched
 */
export class AlreadyPatchedError extends ThemeError {
	constructor(message?: string) {
		super(message ?? 'Firmware is already patched. Use force=true to override.');
		this.name = 'AlreadyPatchedError';
		Object.setPrototypeOf(this, AlreadyPatchedError.prototype);
	}

	getErrorCode(): string {
		return 'ALREADY_PATCHED';
	}
}

/**
 * Capacity error - insufficient space for patch
 */
export class CapacityError extends ThemeError {
	constructor(message: string) {
		super(message);
		this.name = 'CapacityError';
		Object.setPrototypeOf(this, CapacityError.prototype);
	}

	getErrorCode(): string {
		return 'CAPACITY_ERROR';
	}
}

/**
 * Safety error - patch would corrupt firmware
 */
export class SafetyError extends ThemeError {
	constructor(message: string) {
		super(message);
		this.name = 'SafetyError';
		Object.setPrototypeOf(this, SafetyError.prototype);
	}

	getErrorCode(): string {
		return 'SAFETY_ERROR';
	}
}

/**
 * Compatibility error - firmware cannot be patched
 */
export class CompatibilityError extends ThemeError {
	constructor(message: string) {
		super(message);
		this.name = 'CompatibilityError';
		Object.setPrototypeOf(this, CompatibilityError.prototype);
	}

	getErrorCode(): string {
		return 'COMPATIBILITY_ERROR';
	}
}

/**
 * Encoding error - instruction encoding failed
 */
export class EncodingError extends ThemeError {
	constructor(message: string) {
		super(message);
		this.name = 'EncodingError';
		Object.setPrototypeOf(this, EncodingError.prototype);
	}

	getErrorCode(): string {
		return 'ENCODING_ERROR';
	}
}

/**
 * Decoding error - instruction decoding failed
 */
export class DecodingError extends ThemeError {
	constructor(message: string) {
		super(message);
		this.name = 'DecodingError';
		Object.setPrototypeOf(this, DecodingError.prototype);
	}

	getErrorCode(): string {
		return 'DECODING_ERROR';
	}
}

/**
 * Discovery error - function discovery failed
 */
export class DiscoveryError extends ThemeError {
	constructor(message: string) {
		super(message);
		this.name = 'DiscoveryError';
		Object.setPrototypeOf(this, DiscoveryError.prototype);
	}

	getErrorCode(): string {
		return 'DISCOVERY_ERROR';
	}
}

/**
 * Validation error - input validation failed
 */
export class ValidationError extends ThemeError {
	constructor(message: string) {
		super(message);
		this.name = 'ValidationError';
		Object.setPrototypeOf(this, ValidationError.prototype);
	}

	getErrorCode(): string {
		return 'VALIDATION_ERROR';
	}
}

/**
 * Analysis error - firmware analysis failed
 */
export class AnalysisError extends ThemeError {
	constructor(message: string) {
		super(message);
		this.name = 'AnalysisError';
		Object.setPrototypeOf(this, AnalysisError.prototype);
	}

	getErrorCode(): string {
		return 'ANALYSIS_ERROR';
	}
}

/**
 * Patch error - firmware patching failed
 */
export class PatchError extends ThemeError {
	constructor(message: string) {
		super(message);
		this.name = 'PatchError';
		Object.setPrototypeOf(this, PatchError.prototype);
	}

	getErrorCode(): string {
		return 'PATCH_ERROR';
	}
}

/**
 * Not found error - requested function or data not found
 */
export class NotFoundError extends ThemeError {
	constructor(message: string) {
		super(message);
		this.name = 'NotFoundError';
		Object.setPrototypeOf(this, NotFoundError.prototype);
	}

	getErrorCode(): string {
		return 'NOT_FOUND';
	}
}

/**
 * Check if an error is a ThemeError
 */
export function isThemeError(error: unknown): error is ThemeError {
	return error instanceof ThemeError;
}

/**
 * Get user-friendly error message
 */
export function getErrorMessage(error: unknown): string {
	if (isThemeError(error)) {
		return error.getUserMessage();
	}
	if (error instanceof Error) {
		return error.message;
	}
	return String(error);
}

/**
 * Wrap a non-theme error in a ThemeError
 */
export function wrapError(error: unknown, message?: string): ThemeError {
	if (isThemeError(error)) {
		return error;
	}
	if (error instanceof Error) {
		return new ThemeError(message ?? error.message);
	}
	return new ThemeError(message ?? String(error));
}

/**
 * Create and throw a theme error, wrapping non-theme errors
 *
 * @param error - The error to wrap
 * @param ErrorClass - The error class to instantiate
 * @param message - Optional custom message
 * @throws Never returns, always throws
 */
export function throwThemeError(
	error: unknown,
	ErrorClass: new (message: string) => ThemeError,
	message?: string
): never {
	if (isThemeError(error)) {
		throw error;
	}
	if (error instanceof Error) {
		throw new ErrorClass(message ?? error.message);
	}
	throw new ErrorClass(message ?? String(error));
}
