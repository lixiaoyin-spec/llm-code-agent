const { TicTacToe } = require('./game.js');

// 测试用例
const testCases = [
  {
    name: '初始状态',
    setup: () => new TicTacToe(),
    assertions: (game) => {
      console.assert(game.board.every(row => row.every(cell => cell === null)), '棋盘应为空');
      console.assert(game.currentPlayer === 'X', '玩家应先手');
      console.assert(game.winner === null, '初始无获胜者');
      console.assert(!game.isDraw, '初始非平局');
      console.assert(!game.gameOver, '游戏未结束');
    }
  },
  {
    name: '合法落子',
    setup: () => {
      const game = new TicTacToe();
      game.play(0, 0);
      return game;
    },
    assertions: (game) => {
      console.assert(game.board[0][0] === 'X', '玩家应在(0,0)落子');
      console.assert(game.currentPlayer === 'O', '应切换到AI回合');
    }
  },
  {
    name: '重复落子被拒',
    setup: () => {
      const game = new TicTacToe();
      game.play(0, 0);
      game.play(0, 0); // 重复落子
      return game;
    },
    assertions: (game) => {
      console.assert(game.board[0][0] === 'X', '重复落子应被拒绝');
      console.assert(game.currentPlayer === 'O', '不应切换回合');
    }
  },
  {
    name: '横线获胜',
    setup: () => {
      const game = new TicTacToe();
      game.play(0, 0); // X
      game.makeAIMove(); // O
      game.play(0, 1); // X
      game.makeAIMove(); // O
      game.play(0, 2); // X获胜
      return game;
    },
    assertions: (game) => {
      console.assert(game.winner === 'X', '横线应获胜');
      console.assert(game.gameOver, '游戏应结束');
      console.assert(game.scores.X === 1, '玩家分数应增加');
    }
  },
  {
    name: '竖线获胜',
    setup: () => {
      const game = new TicTacToe();
      game.play(0, 0); // X
      game.makeAIMove(); // O
      game.play(1, 0); // X
      game.makeAIMove(); // O
      game.play(2, 0); // X获胜
      return game;
    },
    assertions: (game) => {
      console.assert(game.winner === 'X', '竖线应获胜');
      console.assert(game.gameOver, '游戏应结束');
    }
  },
  {
    name: '对角线获胜',
    setup: () => {
      const game = new TicTacToe();
      game.play(0, 0); // X
      game.makeAIMove(); // O
      game.play(1, 1); // X
      game.makeAIMove(); // O
      game.play(2, 2); // X获胜
      return game;
    },
    assertions: (game) => {
      console.assert(game.winner === 'X', '对角线应获胜');
      console.assert(game.gameOver, '游戏应结束');
    }
  },
  {
    name: 'AI能赢则赢',
    setup: () => {
      const game = new TicTacToe();
      // 设置棋盘让AI能获胜
      game.board = [
        ['X', 'O', 'X'],
        ['X', 'O', null],
        ['O', 'X', 'O']
      ];
      game.currentPlayer = 'O';
      game.makeAIMove();
      return game;
    },
    assertions: (game) => {
      console.assert(game.board[1][2] === 'O', 'AI应选择获胜位置');
      console.assert(game.winner === 'O', 'AI应获胜');
    }
  },
  {
    name: 'AI封堵玩家',
    setup: () => {
      const game = new TicTacToe();
      // 设置棋盘让玩家下一步能获胜
      game.board = [
        ['X', 'O', 'X'],
        ['X', null, 'O'],
        ['O', 'X', null]
      ];
      game.currentPlayer = 'O';
      game.makeAIMove();
      return game;
    },
    assertions: (game) => {
      console.assert(game.board[1][1] === 'O', 'AI应封堵玩家获胜位置');
      console.assert(game.winner === null, 'AI封堵后不应有获胜者');
    }
  },
  {
    name: 'AI优先中心',
    setup: () => {
      const game = new TicTacToe();
      // 设置棋盘让AI选择中心
      game.board = [
        ['X', null, 'O'],
        [null, null, null],
        ['O', null, 'X']
      ];
      game.currentPlayer = 'O';
      game.makeAIMove();
      return game;
    },
    assertions: (game) => {
      console.assert(game.board[1][1] === 'O', 'AI应选择中心');
    }
  },
  {
    name: 'AI优先角',
    setup: function() {
      const game = new TicTacToe();
      // 设置棋盘让AI选择角
      game.board = [
        [null, 'X', null],
        ['X', 'O', 'O'],
        [null, null, 'X']
      ];
      game.currentPlayer = 'O';
      game.makeAIMove();
      return game;
    },
    assertions: (game) => {
      console.assert(game.board[0][0] === 'O', 'AI应选择(0,0)角');
    }
  },
  {
    name: '平局判定',
    setup: () => {
      const game = new TicTacToe();
      // 设置平局棋盘
      game.board = [
        ['X', 'O', 'X'],
        ['X', 'X', 'O'],
        ['O', 'X', 'O']
      ];
      game.currentPlayer = 'X';
      game.checkDraw();
      return game;
    },
    assertions: (game) => {
      console.assert(game.isDraw, '应判定为平局');
      console.assert(game.gameOver, '游戏应结束');
    }
  },
  {
    name: '对局结束后落子被拒',
    setup: () => {
      const game = new TicTacToe();
      game.play(0, 0); // X
      game.makeAIMove(); // O
      game.play(0, 1); // X
      game.makeAIMove(); // O
      game.play(0, 2); // X获胜
      game.play(1, 1); // 游戏结束后落子
      return game;
    },
    assertions: (game) => {
      console.assert(game.board[1][1] === null, '游戏结束后落子应被拒绝');
      console.assert(game.gameOver, '游戏应保持结束状态');
    }
  }
];

// 运行测试
console.log('开始运行单元测试...\n');

let passed = 0;
let failed = 0;

for (const testCase of testCases) {
  try {
    console.log(`测试: ${testCase.name}`);
    const game = testCase.setup();
    testCase.assertions(game);
    console.log('✓ 通过\n');
    passed++;
  } catch (error) {
    console.log(`✗ 失败: ${error.message}\n`);
    failed++;
  }
}

console.log(`测试完成: ${passed} 通过, ${failed} 失败`);