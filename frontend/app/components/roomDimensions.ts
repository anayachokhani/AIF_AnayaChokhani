import policy from "../../shared/room-dimensions.json";
export type RoomUnit = "ft" | "m" | "cm";
const factors = { ft: 30.48, m: 100, cm: 1 };
const roundUpHalf = (value: number) => Math.ceil((value - 1e-9) * 2) / 2;
export function roomLimits(roomType: string, unit: RoomUnit) {
  const rule = policy.rooms[roomType as keyof typeof policy.rooms] ?? policy.rooms.living_room;
  return { ...rule, minSide: rule.minSideCm / factors[unit], minHeight: rule.minHeightCm / factors[unit], maxSide: policy.maxSideCm / factors[unit] };
}
export function convertRoomUnit(value: number, from: RoomUnit, to: RoomUnit) {
  return Math.round(value * factors[from] / factors[to] * 1000000) / 1000000;
}
export function roomDimensionFieldErrors(roomType: string, width: number, depth: number, unit: RoomUnit, height?: number) {
  const limits = roomLimits(roomType, unit);
  const errors: { width?: string; depth?: string; height?: string } = {};
  const factor = factors[unit];
  const validWidth = Number.isFinite(width) && width > 0;
  const validDepth = Number.isFinite(depth) && depth > 0;
  if (!validWidth) errors.width = "Enter a positive width.";
  if (!validDepth) errors.depth = "Enter a positive length.";
  if (validWidth && width * factor > policy.maxSideCm + .0001) errors.width = "Maximum width is 80 ft (24.384 m).";
  if (validDepth && depth * factor > policy.maxSideCm + .0001) errors.depth = "Maximum length is 80 ft (24.384 m).";
  const widthTooShort = validWidth && width * factor + .0001 < limits.minSideCm;
  const depthTooShort = validDepth && depth * factor + .0001 < limits.minSideCm;
  const areaTooSmall = validWidth && validDepth && width * depth * factor * factor / 10000 + .000001 < limits.minAreaM2;
  if (widthTooShort || (areaTooSmall && !depthTooShort)) {
    const suggested = Math.max(limits.minSideCm / factor, validDepth ? limits.minAreaM2 * 10000 / (depth * factor * factor) : 0);
    errors.width = `Try a width of ${roundUpHalf(suggested)} ${unit} or more${areaTooSmall ? " to meet the minimum floor area" : ""}.`;
  }
  if (depthTooShort || (areaTooSmall && !widthTooShort)) {
    const suggested = Math.max(limits.minSideCm / factor, validWidth ? limits.minAreaM2 * 10000 / (width * factor * factor) : 0);
    errors.depth = `Try a length of ${roundUpHalf(suggested)} ${unit} or more${areaTooSmall ? " to meet the minimum floor area" : ""}.`;
  }
  if (height !== undefined) {
    if (!Number.isFinite(height) || height <= 0) errors.height = "Enter a positive height.";
    else if (height * factor + .0001 < limits.minHeightCm) errors.height = `Minimum clear height: ${roundUpHalf(limits.minHeightCm / factor)} ${unit}.`;
  }
  return errors;
}
export function roomDimensionError(roomType: string, width: number, depth: number, unit: RoomUnit, height?: number) {
  return Object.values(roomDimensionFieldErrors(roomType, width, depth, unit, height)).join(" ");
}
