using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class PortableLauncher {
    [STAThread]
    private static void Main() {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string runtime = Path.Combine(root, "runtime", "pythonw.exe");
        string entry = Path.Combine(root, "start.py");
        if (!File.Exists(runtime) || !File.Exists(entry)) {
            MessageBox.Show("请先完整解压文件夹，再启动森林小博士。", "森林小博士");
            return;
        }
        // Use the tested private runtime consistently on classroom computers.
        try {
            var p = new ProcessStartInfo(runtime, "\"" + entry + "\"");
            p.WorkingDirectory = root;
            p.UseShellExecute = false;
            p.CreateNoWindow = true;
            Process.Start(p);
        } catch (Exception ex) {
            MessageBox.Show("启动失败：" + ex.Message, "森林小博士");
        }
    }
}
