import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const policy = JSON.parse(fs.readFileSync(new URL('../shared/room-dimensions.json', import.meta.url), 'utf8'));
const source = fs.readFileSync(new URL('../app/components/roomDimensions.ts', import.meta.url), 'utf8').replace(/import policy from .*?;/, `const policy = ${JSON.stringify(policy)};`);
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { roomLimits, roomDimensionError, roomDimensionFieldErrors, convertRoomUnit } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('every room rejects a short side, insufficient area and insufficient ceiling height', () => {
  for (const [room, limits] of Object.entries(policy.rooms)) {
    for (const unit of ['cm', 'm', 'ft']) {
      const width = convertRoomUnit(limits.minSideCm, 'cm', unit);
      const depth = convertRoomUnit(limits.minAreaM2 * 10000 / limits.minSideCm + .1, 'cm', unit);
      const height = roomLimits(room, unit).minHeight;
      assert.equal(roomDimensionError(room, width, depth, unit, height), '', `${room} ${unit}`);
      assert.notEqual(roomDimensionError(room, width * .9, depth, unit, height), '');
      assert.notEqual(roomDimensionError(room, width, depth * .9, unit, height), '');
      assert.notEqual(roomDimensionError(room, width, depth, unit, height * .9), '');
    }
  }
});

test('changing units preserves the measured room rather than reinterpreting its numbers', () => {
  assert.equal(convertRoomUnit(10, 'ft', 'cm'), 304.8);
  assert.equal(convertRoomUnit(10, 'ft', 'm'), 3.048);
  assert.equal(convertRoomUnit(3.048, 'm', 'ft'), 10);
  assert.notEqual(roomDimensionError('bathroom', NaN, 300, 'cm'), '');
  assert.notEqual(roomDimensionError('living_room', 25, 25, 'm'), '');
});


test('errors identify only failing fields and show half-unit suggestions', () => {
  const errors = roomDimensionFieldErrors('living_room', 7, 18, 'ft', 9);
  assert.equal(errors.width, 'Try a width of 8 ft or more.');
  assert.equal(errors.height, 'Minimum clear height: 9.5 ft.');
  assert.equal(errors.depth, undefined);
  assert.deepEqual(roomDimensionFieldErrors('living_room', 14, 18, 'ft', 10), {});
  const areaErrors = roomDimensionFieldErrors('living_room', 8, 10, 'ft', 10);
  assert.match(areaErrors.width, /10.5 ft/);
  assert.match(areaErrors.depth, /13 ft/);
  assert.equal(areaErrors.height, undefined);
});
