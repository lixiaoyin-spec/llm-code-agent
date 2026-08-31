class TicTacToe {
  constructor() {
    this.board = Array(3).fill(null).map(() => Array(3).fill(null));
    this.currentPlayer = 'X'; // 玩家先手
    this.winner = null;
    this.isDraw = false;
    this.gameOver = false;
    this.scores = { X: 0, O: 0 };
  }

  // 重置游戏
  reset() {
    this.board = Array(3).fill(null).map(() => Array(3).fill(null));
    this.currentPlayer = 'X';
    this.winner = null;
    this.isDraw = false;
    this.gameOver = false;
  }

  // 检查是否有获胜者
  checkWinner(board = this.board) {
    // 检查行
    for (let y = 0; y < 3; y++) {
      if (board[y][0] && board[y][0] === board[y][1] && board[y][1] === board[y][2]) {
        return board[y][0];
      }
    }

    // 检查列
    for (let x = 0; x < 3; x++) {
      if (board[0][x] && board[0][x] === board[1][x] && board[1][x] === board[2][x]) {
        return board[0][x];
      }
    }

    // 检查对角线
    if (board[0][0] && board[0][0] === board[1][1] && board[1][1] === board[2][2]) {
      return board[0][0];
    }
    if (board[0][2] && board[0][2] === board[1][1] && board[1][1] === board[2][0]) {
      return board[0][2];
    }

    return null;
  }

  // 检查是否平局
  checkDraw(board = this.board) {
    return board.every(row => row.every(cell => cell !== null)) && !this.checkWinner(board);
  }

  // 玩家落子
  play(x, y) {
    if (this.gameOver || this.board[y][x] !== null) {
      return false;
    }

    this.board[y][x] = this.currentPlayer;
    
    // 检查游戏结果
    this.winner = this.checkWinner();
    this.isDraw = this.checkDraw();
    
    if (this.winner || this.isDraw) {
      this.gameOver = true;
      if (this.winner) {
        this.scores[this.winner]++;
      }
    } else {
      // 切换到AI回合
      this.currentPlayer = 'O';
    }

    return true;
  }

  // AI落子策略
  aiMove() {
    if (this.gameOver) return null;

    // 1. 能赢则赢
    for (let y = 0; y < 3; y++) {
      for (let x = 0; x < 3; x++) {
        if (this.board[y][x] === null) {
          this.board[y][x] = 'O';
          if (this.checkWinner() === 'O') {
            this.board[y][x] = null; // 恢复
            return { x, y };
          }
          this.board[y][x] = null; // 恢复
        }
      }
    }

    // 2. 否则堵玩家
    for (let y = 0; y < 3; y++) {
      for (let x = 0; x < 3; x++) {
        if (this.board[y][x] === null) {
          this.board[y][x] = 'X';
          if (this.checkWinner() === 'X') {
            this.board[y][x] = null; // 恢复
            return { x, y };
          }
          this.board[y][x] = null; // 恢复
        }
      }
    }

    // 3. 否则优先下中心 (1,1)
    if (this.board[1][1] === null) {
      return { x: 1, y: 1 };
    }

    // 4. 否则按顺序下角：(0,0)、(0,2)、(2,0)、(2,2)
    const corners = [
      { x: 0, y: 0 },
      { x: 0, y: 2 },
      { x: 2, y: 0 },
      { x: 2, y: 2 }
    ];
    for (const corner of corners) {
      if (this.board[corner.y][corner.x] === null) {
        return corner;
      }
    }

    // 5. 否则按顺序下边：(0,1)、(1,0)、(1,2)、(2,1)
    const edges = [
      { x: 0, y: 1 },
      { x: 1, y: 0 },
      { x: 1, y: 2 },
      { x: 2, y: 1 }
    ];
    for (const edge of edges) {
      if (this.board[edge.y][edge.x] === null) {
        return edge;
      }
    }

    return null; // 没有可用位置（理论上不会发生）
  }

  // 执行AI移动
  makeAIMove() {
    const move = this.aiMove();
    if (move) {
      this.board[move.y][move.x] = 'O';
      
      // 检查游戏结果
      this.winner = this.checkWinner();
      this.isDraw = this.checkDraw();
      
      if (this.winner || this.isDraw) {
        this.gameOver = true;
        if (this.winner) {
          this.scores[this.winner]++;
        }
      } else {
        // 切换回玩家回合
        this.currentPlayer = 'X';
      }
      
      return move;
    }
    return null;
  }

  // 获取棋盘状态字符串（用于显示）
  getBoardString() {
    const symbols = {
      null: ' ',
      'X': 'X',
      'O': 'O'
    };
    
    let result = '';
    for (let y = 0; y < 3; y++) {
      for (let x = 0; x < 3; x++) {
        result += symbols[this.board[y][x]];
        if (x < 2) result += '|';
      }
      if (y < 2) result += '\n-----\n';
    }
    return result;
  }
}

// CommonJS导出
if (typeof module !== 'undefined') {
  module.exports = { TicTacToe };
}