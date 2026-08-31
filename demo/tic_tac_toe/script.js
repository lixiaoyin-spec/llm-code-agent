// 导入游戏逻辑
const { TicTacToe } = require('./game.js');

// 创建游戏实例
const game = new TicTacToe();

// DOM元素
const board = document.getElementById('board');
const cells = document.querySelectorAll('.cell');
const status = document.getElementById('status');
const scoreX = document.getElementById('scoreX');
const scoreO = document.getElementById('scoreO');
const restartBtn = document.getElementById('restartBtn');

// 更新显示
function updateDisplay() {
    // 更新棋盘
    cells.forEach(cell => {
        const x = parseInt(cell.dataset.x);
        const y = parseInt(cell.dataset.y);
        const value = game.board[y][x];
        
        cell.textContent = value || '';
        cell.className = 'cell';
        
        if (value) {
            cell.classList.add('taken', value.toLowerCase());
        }
    });

    // 更新状态
    if (game.gameOver) {
        if (game.winner) {
            status.textContent = `游戏结束！${game.winner === 'X' ? '玩家' : '电脑'} 获胜！`;
        } else {
            status.textContent = '游戏结束！平局！';
        }
    } else {
        status.textContent = `轮到${game.currentPlayer === 'X' ? '玩家' : '电脑'} ${game.currentPlayer}`;
    }

    // 更新分数
    scoreX.textContent = game.scores.X;
    scoreO.textContent = game.scores.O;
}

// 玩家点击格子
function handleCellClick(event) {
    const cell = event.target;
    if (!cell.classList.contains('cell') || cell.classList.contains('taken')) {
        return;
    }

    const x = parseInt(cell.dataset.x);
    const y = parseInt(cell.dataset.y);

    // 玩家落子
    if (game.play(x, y)) {
        updateDisplay();
        
        // 如果游戏未结束，AI延迟300ms后落子
        if (!game.gameOver) {
            setTimeout(() => {
                game.makeAIMove();
                updateDisplay();
            }, 300);
        }
    }
}

// 重新开始游戏
function handleRestart() {
    game.reset();
    updateDisplay();
}

// 事件监听
board.addEventListener('click', handleCellClick);
restartBtn.addEventListener('click', handleRestart);

// 初始化显示
updateDisplay();