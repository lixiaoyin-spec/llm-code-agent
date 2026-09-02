const fs = require("fs");
const { TicTacToe } = require("./game.js");

function renderBoard(board) {
  return board
    .map((row) => row.map((c) => (c === null ? " " : c)).join(" | "))
    .join("\n");
}

function printStatus(game) {
  if (game.winner) {
    return `${game.winner === "X" ? "玩家 X" : "电脑 O"} 获胜！`;
  }
  if (game.isDraw) {
    return "平局！";
  }
  return game.currentPlayer === "X" ? "轮到玩家 X" : "电脑思考中…";
}

function main() {
  const file = process.argv[2];
  if (!file) {
    console.error("用法: node simulate.js <指令文件>");
    process.exit(1);
  }

  const content = fs.readFileSync(file, "utf8");
  const lines = content
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  const game = new TicTacToe();
  let scores = { X: 0, O: 0 };

  console.log("=== 井字棋模拟 ===\n玩家 X 先手\n");

  for (const line of lines) {
    const parts = line.split(",");
    const x = parseInt(parts[0], 10);
    const y = parseInt(parts[1], 10);
    if (Number.isNaN(x) || Number.isNaN(y)) {
      console.log(`无效指令：${line}`);
      continue;
    }

    console.log(`玩家落子 (${x}, ${y})：`);
    const result = game.play(x, y);
    if (result === null) {
      console.log("落子无效（已有棋子或对局已结束）\n");
      continue;
    }
    console.log(renderBoard(game.board));
    console.log(printStatus(game));
    if (game.isOver) break;

    const move = game.aiMove();
    if (move) {
      console.log(`\n电脑落子 (${move.x}, ${move.y})：`);
      console.log(renderBoard(game.board));
      console.log(printStatus(game));
      if (game.isOver) break;
    }
  }

  if (game.winner === "X") scores.X = 1;
  else if (game.winner === "O") scores.O = 1;

  console.log("\n=== 最终结果 ===");
  if (game.winner) {
    console.log(`胜者：${game.winner === "X" ? "玩家 X" : "电脑 O"}`);
  } else if (game.isDraw) {
    console.log("平局");
  } else {
    console.log("对局未结束（指令用完）");
  }
  console.log(`得分：玩家 X ${scores.X} - 电脑 O ${scores.O}`);

  process.exit(0);
}

main();
