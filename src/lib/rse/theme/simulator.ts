/**
 * Control Flow Simulator
 *
 * Simulates execution of Thumb instructions to trace theme color values.
 */

import type { Instruction } from './thumb/index.js';
import { ThumbDecoder } from './thumb/index.js';
import { InstructionType } from './thumb/instructions.js';
import type { ColorWrite, MovwRecord } from './types.js';

/**
 * Control Flow Simulator Class
 */
export class ControlFlowSimulator {
	constructor(private readonly decoder: ThumbDecoder) {}

	/**
	 * Simulate function execution with a given theme value
	 */
	simulate(
		funcAddr: number,
		endAddr: number,
		themeValue: number
	): [Map<number, number>, ColorWrite[], MovwRecord[]] {
		const registers = new Map<number, number>();
		for (let i = 0; i < 16; i++) {
			registers.set(i, 0);
		}
		registers.set(0, themeValue);

		const registerSources = new Map<number, MovwRecord | null>();
		for (let i = 0; i < 16; i++) {
			registerSources.set(i, null);
		}

		const colorWrites: ColorWrite[] = [];
		const movwRecords: MovwRecord[] = [];
		const seenAddrs = new Set<number>();
		let lastCmpResult = false;
		let itBlockRemaining = 0;
		const itConditions: boolean[] = [];
		let currentThemeCondition: number | null = null;

		let addr = funcAddr;
		const maxSteps = 500;

		for (let step = 0; step < maxSteps && addr < endAddr;) {
			// Prevent infinite loops
			if (seenAddrs.has(addr)) {
				break;
			}
			seenAddrs.add(addr);

			const instr = this.decoder.decode(addr);
			const instrSize = instr.size;

			// Handle IT block instructions
			if (itBlockRemaining > 0) {
				const condIdx = itConditions.length - itBlockRemaining;
				if (condIdx >= 0 && condIdx < itConditions.length && itConditions[condIdx]) {
					this.executeInstructionInItBlock(
						instr,
						addr,
						registers,
						registerSources,
						themeValue,
						currentThemeCondition,
						colorWrites,
						movwRecords
					);
				}

				itBlockRemaining--;
				addr += instrSize;
				step++;
				continue;
			}

			// Handle normal instructions
			const result = this.executeInstruction(
				instr,
				addr,
				registers,
				registerSources,
				themeValue,
				currentThemeCondition,
				colorWrites,
				movwRecords,
				lastCmpResult,
				itConditions
			);

			// Update state from instruction execution
			if (result.newCmpResult !== null) {
				lastCmpResult = result.newCmpResult;
			}
			if (result.newItBlockRemaining !== null) {
				itBlockRemaining = result.newItBlockRemaining;
			}

			// Handle branch target
			if (result.branchTo !== null) {
				addr = result.branchTo;
			} else {
				addr += instrSize;
			}
			step++;
		}

		return [registers, colorWrites, movwRecords];
	}

	/**
	 * Execute an instruction
	 */
	private executeInstruction(
		instr: Instruction,
		addr: number,
		registers: Map<number, number>,
		registerSources: Map<number, MovwRecord | null>,
		themeValue: number,
		currentThemeCondition: number | null,
		colorWrites: ColorWrite[],
		movwRecords: MovwRecord[],
		lastCmpResult: boolean,
		itConditions: boolean[]
	): { newCmpResult: boolean | null; newItBlockRemaining: number | null; branchTo: number | null } {
		let newCmpResult: boolean | null = null;
		let newItBlockRemaining: number | null = null;
		let branchTo: number | null = null;

		switch (instr.instrType) {
			case InstructionType.PUSH:
				// Ignore
				break;

			case InstructionType.POP:
				// Ignore
				break;

			case InstructionType.BX:
				// Would return from function - stop simulation
				break;

			case InstructionType.MOVW:
				this.handleMovw(instr, addr, registers, registerSources, movwRecords, currentThemeCondition);
				break;

			case InstructionType.MOVS:
				registers.set(instr.rd, instr.imm);
				break;

			case InstructionType.CMP:
				if (instr.rn >= 0 && instr.rn < 16) {
					newCmpResult = (registers.get(instr.rn) ?? 0) === instr.imm;
				}
				break;

			case InstructionType.BEQ:
				// Branch if equal
				if (lastCmpResult) {
					branchTo = this.getBranchTarget(instr);
				}
				break;

			case InstructionType.BNE:
				// Branch if not equal
				if (!lastCmpResult) {
					branchTo = this.getBranchTarget(instr);
				}
				break;

			case InstructionType.B:
				// Unconditional branch
				branchTo = this.getBranchTarget(instr);
				break;

			case InstructionType.CBZ:
			case InstructionType.CBNZ:
				// Compare and branch on zero/non-zero - not fully tracked
				break;

			case InstructionType.IT:
				newItBlockRemaining = this.setupItBlock(instr, lastCmpResult, itConditions);
				break;

			case InstructionType.STRH:
			case InstructionType.STRH_W:
				this.handleStrh(instr, registers, themeValue, registerSources, colorWrites);
				break;
		}

		return { newCmpResult, newItBlockRemaining, branchTo };
	}

	/**
	 * Execute instruction inside IT block
	 */
	private executeInstructionInItBlock(
		instr: Instruction,
		addr: number,
		registers: Map<number, number>,
		registerSources: Map<number, MovwRecord | null>,
		themeValue: number,
		currentThemeCondition: number | null,
		colorWrites: ColorWrite[],
		movwRecords: MovwRecord[]
	): void {
		switch (instr.instrType) {
			case InstructionType.STRH:
			case InstructionType.STRH_W:
				this.handleStrh(instr, registers, themeValue, registerSources, colorWrites);
				break;

			case InstructionType.MOVW:
				this.handleMovw(instr, addr, registers, registerSources, movwRecords, currentThemeCondition);
				break;

			case InstructionType.POP:
				// Check for POP {..., PC} which would return
				const hw = this.decoder['readU16'](addr);
				if (hw & 0x100) {
					// Would return - stop simulation for this function
				}
				break;

			case InstructionType.BX:
				// Would return - stop simulation
				break;
		}
	}

	/**
	 * Handle MOVW instruction
	 */
	private handleMovw(
		instr: Instruction,
		addr: number,
		registers: Map<number, number>,
		registerSources: Map<number, MovwRecord | null>,
		movwRecords: MovwRecord[],
		themeCondition: number | null
	): void {
		const record: MovwRecord = {
			addr,
			instr,
			colorValue: instr.imm,
			targetReg: instr.rd,
			themeCondition
		};

		movwRecords.push(record);
		registerSources.set(instr.rd, record);
		registers.set(instr.rd, instr.imm);
	}

	/**
	 * Handle STRH instruction
	 */
	private handleStrh(
		instr: Instruction,
		registers: Map<number, number>,
		themeValue: number,
		registerSources: Map<number, MovwRecord | null>,
		colorWrites: ColorWrite[]
	): void {
		const rt = instr.rd >= 0 ? instr.rd : 0;
		const rn = instr.rn >= 0 ? instr.rn : 0;
		const color = registers.get(rt) ?? 0;
		const movwInstr = registerSources.get(rt) ?? null;

		const write: ColorWrite = {
			addr: instr.addr,
			instr,
			colorValue: color,
			targetReg: rn,
			sourceReg: rt,
			themeCondition: themeValue,
			movwInstr
		};

		colorWrites.push(write);
	}

	/**
	 * Setup IT block
	 */
	private setupItBlock(
		instr: Instruction,
		cmpResult: boolean,
		itConditions: boolean[]
	): number {
		const mask = instr.itMask;
		const firstcond = instr.cond;

		const size = this.getItBlockSize(mask);
		itConditions.length = 0;

		const fcLsb = firstcond & 1;
		const condTrue = (firstcond === 0 && cmpResult) || (firstcond === 1 && !cmpResult);
		itConditions.push(condTrue);

		for (let i = 1; i < size; i++) {
			const bitPos = 4 - i;
			const maskBit = (mask >> bitPos) & 1;

			if (maskBit === fcLsb) {
				itConditions.push(condTrue);
			} else {
				itConditions.push(!condTrue);
			}
		}

		return size;
	}

	/**
	 * Get IT block size from mask
	 */
	private getItBlockSize(mask: number): number {
		if (mask === 0) return 0;
		if (mask & 0x1) return 4;
		if (mask & 0x2) return 3;
		if (mask & 0x4) return 2;
		return 1;
	}

	/**
	 * Calculate branch target address for branch instructions
	 */
	private getBranchTarget(instr: Instruction): number {
		// The decoder already calculates the absolute branch target
		return instr.branchTarget;
	}
}
