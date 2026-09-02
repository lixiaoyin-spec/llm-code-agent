// 井字棋核心逻辑（浏览器与 Node 共用）

/**
 * 判定当前棋盘的胜者。
 * 返回 "X" / "O"，无人获胜返回 null。
 */
function checkWinner(board) {
  const lines = [];

  // 3 行
  for (let y = 0; y < 3; y++) {
    lines.push([board[y][0], board[y][1], board[y][2]]);
  }
  // 3 列
  for (let x = 0; x < 3; x++) {
    lines.push([board[0][x], board[1][x], board[2][x]]);
  }
  // 2 条对角线
  lines.push([board[0][0], board[1][1], board[2][2]]);
  lines.push([board[0][2], board[1][1], board[2][0]]);

  for (const [a, b, c] of lines) {
    if (a !== null && a === b && b === c) {
      return a;
    }
  }
  return null;
}

class TicTacToe {
  constructor() {
    // board[y][x]：null 为空，"X" 玩家，"O" 电脑
    this.board = [
      [null, null, null],
      [null, null, null],
      [null, null, null],
    ];
    this.currentPlayer = "X"; // 玩家 X 先手
  }

  get winner() {
    return checkWinner(this.board);
  }

  get isDraw() {
    const full = this.board.every((row) => row.every((cell) => cell !== null));
    return this.winner === null && full;
  }

  get isOver() {
    return this.winner !== null || this.isDraw;
  }

  /** 玩家落子，返回本步结果；无效落子返回 null */
  play(x, y) {
    if (this.isOver) return null;
    if (!Number.isInteger(x) || !Number.isInteger(y)) return null;
    if (x < 0 || x > 2 || y < 0 || y > 2) return null;
    if (this.board[y][x] !== null) return null;

    this.board[y][x] = "X";
    this.currentPlayer = "O";
    return { winner: this.winner, isDraw: this.isDraw };
  }

  /** 电脑按固定优先级落子，返回落子坐标 {x, y}；无法落子返回 null */
  aiMove() {
    if (this.isOver) return null;
    const move = this._chooseMove();
    if (!move) return null;

    this.board[move.y][move.x] = "O";
    this.currentPlayer = "X";
    return move;
  }

  _chooseMove() {
    // 1) 能赢则赢
    const win = this._findWinningCell("O");
    if (win) return win;
    // 2) 堵玩家
    const block = this._findWinningCell("X");
    if (block) return block;
    // 3) 中心
    if (this.board[1][1] === null) return { x: 1, y: 1 };
    // 4) 角（顺序固定，坐标为 (x, y)，x 为列、y 为行）
    const corners = [
      { x: 0, y: 0 },
      { x: 0, y: 2 },
      { x: 2, y: 0 },
      { x: 2, y: 2 },
    ];
    for (const c of corners) {
      if (this.board[c.y][c.x] === null) return c;
    }
    // 5) 边（顺序固定，坐标为 (x, y)）
    const edges = [
      { x: 0, y: 1 },
      { x: 1, y: 0 },
      { x: 1, y: 2 },
      { x: 2, y: 1 },
    ];
    for (const c of edges) {
      if (this.board[c.y][c.x] === null) return c;
    }
    return null;
  }

  /** 找到 player 落子即可三连的空位（行优先），否则返回 null */
  _findWinningCell(player) {
    for (let y = 0; y < 3; y++) {
      for (let x = 0; x < 3; x++) {
        if (this.board[y][x] === null) {
          this.board[y][x] = player;
          const win = checkWinner(this.board) === player;
          this.board[y][x] = null;
          if (win) return { x, y };
        }
      }
    }
    return null;
  }
}

// ---- 浏览器渲染与交互 ----
if (typeof document !== "undefined") {
  let game = new TicTacToe();
  let scores = { X: 0, O: 0 };

  function init() {
    const boardEl = document.getElementById("board");
    const statusEl = document.getElementById("status");
    const scoreEl = document.getElementById("score");
    const restartBtn = document.getElementById("restart");

    function render() {
      boardEl.innerHTML = "";
      for (let y = 0; y < 3; y++) {
        for (let x = 0; x < 3; x++) {
          const cell = document.createElement("button");
          cell.className = "cell";
          cell.textContent = game.board[y][x] || "";
          cell.disabled =
            game.isOver ||
            game.board[y][x] !== null ||
            game.currentPlayer !== "X";
          cell.addEventListener("click", () => handleClick(x, y));
          boardEl.appendChild(cell);
        }
      }

      if (game.winner) {
        statusEl.textContent =
          game.winner === "X" ? "玩家 X 获胜！" : "电脑 O 获胜！";
      } else if (game.isDraw) {
        statusEl.textContent = "平局！";
      } else if (game.currentPlayer === "X") {
        statusEl.textContent = "轮到玩家 X";
      } else {
        statusEl.textContent = "电脑思考中…";
      }

      scoreEl.textContent = `玩家 X：${scores.X}　电脑 O：${scores.O}`;
    }

    function updateScore() {
      if (game.isOver && game.winner) {
        scores[game.winner]++;
      }
    }

    function handleClick(x, y) {
      if (game.currentPlayer !== "X" || game.isOver) return;
      const result = game.play(x, y);
      if (result === null) return;

      updateScore();
      render();

      if (!game.isOver) {
        setTimeout(() => {
          game.aiMove();
          updateScore();
          render();
        }, 300);
      }
    }

    restartBtn.addEventListener("click", () => {
      game = new TicTacToe();
      render();
    });

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}

// ---- CommonJS 导出（供 Node 测试与命令行模拟使用）----
if (typeof module !== "undefined" && module.exports) {
  module.exports = { TicTacToe, checkWinner };
}
