// Bottom-right "controls" strip, like ↑↓ SELECT / A CONFIRM / B CLOSE in the game menu.
export default function ControlHints() {
  return (
    <ul className="hints" aria-hidden="true">
      <li><b>↵</b>FIND</li>
      <li><b>●</b>SELECT</li>
      <li><b>✥</b>MOVE</li>
    </ul>
  );
}
