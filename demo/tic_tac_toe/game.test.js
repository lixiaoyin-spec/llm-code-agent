const { test } = require("node:test");
const assert = require("node:assert");
const { TicTacToe, checkWinner } = require("./game.js");

test("合法落子", () => {
  const g = new TicTacToe();
  const result = g.play(0, 0);
  assert.strictEqual(g.board[0][0], "X");
  assert.notStrictEqual(result, null);
  assert.strictEqual(result.winner, null);
  assert.strictEqual(result.isDraw, false);
});

test("重复落子被拒", () => {
  const g = new TicTacToe();
  g.play(0, 0);
  const result = g.play(0, 0);
  assert.strictEqual(result, null);
  assert.strictEqual(g.board[0][0], "X");
});

test("横线获胜", () => {
  const g = new TicTacToe();
  g.board = [
    ["X", "X", null],
    ["O", "O", null],
    [null, null, null],
  ];
  g.play(2, 0);
  assert.strictEqual(g.winner, "X");
});

test("竖线获胜", () => {
  const g = new TicTacToe();
  g.board = [
    ["X", "O", null],
    ["X", "O", null],
    [null, null, null],
  ];
  g.play(0, 2);
  assert.strictEqual(g.winner, "X");
});

test("主对角线获胜", () => {
  const g = new TicTacToe();
  g.board = [
    ["X", "O", null],
    [null, "X", null],
    ["O", null, null],
  ];
  g.play(2, 2);
  assert.strictEqual(g.winner, "X");
});

test("反对角线获胜", () => {
  const g = new TicTacToe();
  g.board = [
    [null, "O", "X"],
    [null, "X", "O"],
    [null, null, null],
  ];
  g.play(0, 2);
  assert.strictEqual(g.winner, "X");
});

test("checkWinner 独立函数识别反对角线", () => {
  const board = [
    [null, null, "X"],
    [null, "X", null],
    ["X", null, null],
  ];
  assert.strictEqual(checkWinner(board), "X");
});

test("AI 能赢则赢", () => {
  const g = new TicTacToe();
  g.board = [
    ["O", "O", null],
    ["X", "X", null],
    [null, null, null],
  ];
  const move = g.aiMove();
  assert.deepStrictEqual(move, { x: 2, y: 0 });
  assert.strictEqual(g.winner, "O");
});

test("AI 封堵玩家", () => {
  const g = new TicTacToe();
  g.board = [
    ["X", "X", null],
    [null, "O", null],
    [null, null, null],
  ];
  const move = g.aiMove();
  assert.deepStrictEqual(move, { x: 2, y: 0 });
  assert.strictEqual(g.board[0][2], "O");
});

test("AI 多个堵位时按行优先取第一个", () => {
  const g = new TicTacToe();
  g.board = [
    ["X", null, null],
    [null, "O", null],
    ["X", null, "X"],
  ];
  const move = g.aiMove();
  assert.deepStrictEqual(move, { x: 0, y: 1 });
});

test("AI 优先下中心", () => {
  const g = new TicTacToe();
  const move = g.aiMove();
  assert.deepStrictEqual(move, { x: 1, y: 1 });
});

test("AI 中心被占后优先下角", () => {
  const g = new TicTacToe();
  g.board = [
    [null, null, null],
    [null, "X", null],
    [null, null, null],
  ];
  const move = g.aiMove();
  assert.deepStrictEqual(move, { x: 0, y: 0 });
});

test("AI 角顺序按 (x,y)：左上、左下、右上、右下", () => {
  const g = new TicTacToe();
  g.board = [
    ["X", null, null],
    [null, "O", null],
    [null, null, null],
  ];
  const move = g.aiMove();
  assert.deepStrictEqual(move, { x: 0, y: 2 });
});

test("平局判定", () => {
  const g = new TicTacToe();
  g.board = [
    ["X", "O", "X"],
    ["X", "O", "O"],
    ["O", "X", "X"],
  ];
  assert.strictEqual(g.winner, null);
  assert.strictEqual(g.isDraw, true);
  assert.strictEqual(g.isOver, true);
});

test("对局结束后落子被拒", () => {
  const g = new TicTacToe();
  g.board = [
    ["X", "X", "X"],
    ["O", "O", null],
    [null, null, null],
  ];
  assert.strictEqual(g.winner, "X");
  const result = g.play(2, 1);
  assert.strictEqual(result, null);
  assert.strictEqual(g.board[1][2], null);
});
