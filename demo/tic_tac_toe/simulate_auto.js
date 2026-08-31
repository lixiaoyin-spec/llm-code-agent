const { TicTacToe } = require('./game.js');
const fs = require('fs');

// 读取指令文件
function readCommands(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    return content.split('\n')
      .map(line => line.trim())
      .filter(line => line && !line.startsWith('#')); // 过滤空行和注释
  } catch (error) {
    console.error(`无法读取指令文件: ${error.message}`);
    process.exit(1);
  }
}

// 解析玩家指令
function parseCommand(command) {
  const parts = command.split(',');
  if (parts.length !== 2) {
    throw new Error(`无效指令格式: ${command}，应为 "x,y"`);
  }
  
  const x = parseInt(parts[0].trim());
  const y = parseInt(parts[1].trim());
  
  if (isNaN(x) || isNaN(y) || x < 0 || x > 2 || y < 0 || y > 2) {
    throw new Error(`坐标超出范围: (${x}, ${y})，应为 0-2`);
  }
  
  return { x, y };
}

// 打印棋盘状态
function printBoard(game) {
  console.log('\n当前棋盘:');
  console.log(game.getBoardString());
}

// 打印游戏状态
function printStatus(game) {
  if (game.gameOver) {
    if (game.winner) {
      console.log(`游戏结束！${game.winner === 'X' ? '玩家' : '电脑'} 获胜！`);
    } else {
      console.log('游戏结束！平局！');
    }
    console.log(`最终比分 - 玩家 X: ${game.scores.X}, 电脑 O: ${game.scores.O}`);
  } else {
    console.log(`当前回合: ${game.currentPlayer === 'X' ? '玩家' : '电脑'} ${game.currentPlayer}`);
  }
}

// 主函数
function main() {
  if (process.argv.length < 3) {
    console.error('用法: node simulate_auto.js <指令文件>');
    process.exit(1);
  }

  const commandFile = process.argv[2];
  const commands = readCommands(commandFile);
  
  console.log(`开始模拟游戏，指令文件: ${commandFile}`);
  console.log(`共 ${commands.length} 条指令\n`);

  const game = new TicTacToe();
  let commandIndex = 0;

  while (commandIndex < commands.length && !game.gameOver) {
    const command = commands[commandIndex];
    
    printBoard(game);
    printStatus(game);
    
    try {
      const { x, y } = parseCommand(command);
      
      console.log(`玩家指令: ${command}`);
      
      if (game.play(x, y)) {
        console.log(`玩家在 (${x}, ${y}) 落子 X`);
        
        if (!game.gameOver) {
          // AI延迟300ms后落子
          setTimeout(() => {
            console.log('AI思考中...');
            const aiMove = game.makeAIMove();
            if (aiMove) {
              console.log(`AI在 (${aiMove.x}, ${aiMove.y}) 落子 O`);
            }
          }, 300);
        }
      } else {
        console.log(`无效落子: (${x}, ${y}) 位置已被占用或游戏已结束`);
      }
      
    } catch (error) {
      console.error(`指令错误: ${error.message}`);
    }
    
    commandIndex++;
    
    // 等待AI落子完成
    if (!game.gameOver && commandIndex < commands.length) {
      console.log('');
      // 简单延迟，让AI有时间落子
      const start = Date.now();
      while (Date.now() - start < 500) {
        // 等待500ms
      }
    }
  }

  // 打印最终状态
  printBoard(game);
  printStatus(game);
  
  console.log('\n模拟完成');
  process.exit(0);
}

// 运行主函数
main();