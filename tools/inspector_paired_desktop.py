"""Pairing-code desktop client. No SSH setup or password entry."""
import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from inspector_pair_client import Connection, OPERATIONS


def main():
    root = tk.Tk(); root.title('MGU Inspector — private pairing'); root.geometry('850x700')
    body = ttk.Frame(root, padding=20); body.pack(fill='both', expand=True)
    ttk.Label(body, text='MGU Inspector 0.2', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
    ttk.Label(body, text='კერძო Tailscale კავშირი • ერთჯერადი კოდი • SSH-ის გარეშე').pack(anchor='w', pady=(4, 18))
    host, code, operation = tk.StringVar(), tk.StringVar(), tk.StringVar(value='report')
    grid = ttk.Frame(body); grid.pack(fill='x')
    for row, label, variable in [(0, 'მანქანის Tailscale IP (100.x.x.x)', host), (1, 'მანქანის ეკრანის 12-ციფრიანი კოდი', code)]:
        ttk.Label(grid, text=label).grid(row=row, column=0, sticky='w', pady=5)
        ttk.Entry(grid, textvariable=variable, show='*' if row == 1 else '').grid(row=row, column=1, sticky='ew', padx=12)
    ttk.Label(grid, text='მონაცემების ჯგუფი').grid(row=2, column=0, sticky='w', pady=5)
    ttk.Combobox(grid, textvariable=operation, values=OPERATIONS, state='readonly').grid(row=2, column=1, sticky='ew', padx=12)
    grid.columnconfigure(1, weight=1)
    status = tk.StringVar(value='მანქანა და ლეპტოპი უნდა იყვნენ ერთ კერძო Tailscale ქსელში. მანქანაში შექმენი კოდი.')
    ttk.Label(body, textvariable=status, wraplength=790).pack(fill='x', pady=15)
    controls = ttk.Frame(body); controls.pack(fill='x')
    output = tk.Text(body, wrap='word', font=('Consolas', 10)); output.pack(fill='both', expand=True, pady=12)
    events = queue.Queue(); connection = [None]; report = [None]
    def work(action, address, pairing_code, op):
        try:
            if action == 'pair':
                c = Connection(address); c.pair(pairing_code); value = c.collect('summary')
                events.put(('ok', c, value))
            elif action == 'collect':
                events.put(('ok', connection[0], connection[0].collect(op)))
            else:
                connection[0].revoke(); events.put(('revoked', None, None))
        except Exception:
            events.put(('error', None, None))
    buttons = []
    def start(action):
        if action != 'pair' and not connection[0]: return
        for b in buttons: b.configure(state='disabled')
        status.set('მოთხოვნა სრულდება…')
        # Read Tk variables only on the UI thread; never log the pairing code/token.
        args = (action, host.get().strip(), code.get().strip(), operation.get())
        threading.Thread(target=work, args=args, daemon=True).start()
    for label, action in [('დაკავშირება', 'pair'), ('მონაცემების წაკითხვა', 'collect'), ('წვდომის გაუქმება', 'revoke')]:
        b = ttk.Button(controls, text=label, command=lambda action=action: start(action)); b.pack(side='left', padx=(0, 8)); buttons.append(b)
    def save():
        if report[0] is None: return
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='mgu-report.json')
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as stream: json.dump(report[0], stream, indent=2, sort_keys=True)
                status.set('ანგარიში შენახულია ლეპტოპზე. ავტომატურად არსად გაგზავნილა.')
            except OSError: status.set('ანგარიშის შენახვა ვერ მოხერხდა.')
    export = ttk.Button(controls, text='შენახვა', command=save); export.pack(side='left')
    def poll():
        try:
            kind, conn, value = events.get_nowait()
            for b in buttons: b.configure(state='normal')
            code.set('')
            if kind == 'ok':
                connection[0], report[0] = conn, value
                output.delete('1.0', 'end'); output.insert('1.0', json.dumps(value, indent=2, sort_keys=True))
                status.set('დაკავშირებულია. სესია მაქსიმუმ 15 წუთია; მანქანიდანაც შეგიძლია გააუქმო.')
            elif kind == 'revoked':
                connection[0] = None; status.set('წვდომა გაუქმებულია.')
            else:
                connection[0] = None
                status.set('ვერ შესრულდა. შეამოწმე Tailscale, მანქანის აპი, ახალი კოდი და Store-ის pending restart. SSH არ არის საჭირო.')
        except queue.Empty: pass
        root.after(150, poll)
    root.after(150, poll); root.mainloop()


if __name__ == '__main__': main()
