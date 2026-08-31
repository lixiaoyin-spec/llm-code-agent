const { SnakeGame } = require('./game.js');
const fs = require('fs');

// 固定随机种子用于模拟
function createSimGame(seed = 42) {
    const random = () => {
        seed = (seed * 9301 + 49297) % 233280;
        return seed / 233280;
    };
    return new SnakeGame(20, 20, random);
}

function renderBoard(board, score) {
    console.log(`分数: ${score}`);
    board.forEach(row => {
        console.log(row.join(''));
    });
}

function simulate(inputFile) {
    const game = createSimGame();
    const lines = fs.readFileSync(inputFile, 'utf8').split('\n').filter(line => line.trim());
    
    for (const line of lines) {
        if (game.gameOver) break;
        
        const directionMap = {
            'right': 'right', 'r': 'right',
            'left': 'left', 'l': 'left', 
            'up': 'up', 'u': 'up',
            'down': 'down', 'd': 'down'
        };
        
        const direction = directionMap[line.toLowerCase()];
        if (direction) {
            const result = game.step(direction);
            
            // 渲染当前状态
            const board = game.getBoard();
            renderBoard(board, game.score);
            console.log();  // 空行分隔
        }
    }
    
    console.log(`游戏结束！总分: ${game.score}`);
}

// 命令行参数处理
const args = process.argv.slice(2);
if (args.length < 1) {
    console.error('用法: node simulate.js <指令文件>');
    process.exit(1);
}

const inputFile = args[0];
simulate(inputFile);