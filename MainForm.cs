using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace WowVersionFix;

public sealed class MainForm : Form
{
    private readonly ComboBox _productBox = new();
    private readonly ComboBox _versionBox = new();
    private readonly CheckBox _chkWowExe = new();
    private readonly CheckBox _chkLoader = new();
    private readonly TextBox _extraFiles = new();
    private readonly TextBox _outputDir = new();
    private readonly Button _browseBtn = new();
    private readonly Button _extractBtn = new();
    private readonly Button _openFolderBtn = new();
    private readonly Button _refreshBtn = new();
    private readonly TextBox _log = new();
    private readonly ProgressBar _progress = new();
    private readonly Label _statusLabel = new();

    private Dictionary<string, List<BuildEntry>> _builds = new();
    private CancellationTokenSource? _runCts;

    public MainForm()
    {
        Text = "WoW Version Fix";
        ClientSize = new Size(760, 560);
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(640, 500);
        Font = new Font("Segoe UI", 9F);

        BuildUi();
        _ = LoadBuildsAsync();
    }

    private void BuildUi()
    {
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(12), ColumnCount = 1, RowCount = 8 };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        for (int i = 0; i < 7; i++) root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        // Product + Refresh
        var row1 = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 1, AutoSize = true };
        row1.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 80));
        row1.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        row1.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        row1.Controls.Add(new Label { Text = "Product:", TextAlign = ContentAlignment.MiddleLeft, AutoSize = false, Dock = DockStyle.Fill }, 0, 0);
        _productBox.DropDownStyle = ComboBoxStyle.DropDownList;
        _productBox.Dock = DockStyle.Fill;
        _productBox.SelectedIndexChanged += (_, _) => RefreshVersionList();
        row1.Controls.Add(_productBox, 1, 0);
        _refreshBtn.Text = "Refresh";
        _refreshBtn.AutoSize = true;
        _refreshBtn.Click += async (_, _) => await LoadBuildsAsync();
        row1.Controls.Add(_refreshBtn, 2, 0);
        root.Controls.Add(row1, 0, 0);

        // Version dropdown
        var row2 = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, AutoSize = true };
        row2.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 80));
        row2.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        row2.Controls.Add(new Label { Text = "Version:", TextAlign = ContentAlignment.MiddleLeft, AutoSize = false, Dock = DockStyle.Fill }, 0, 0);
        _versionBox.DropDownStyle = ComboBoxStyle.DropDownList;
        _versionBox.Dock = DockStyle.Fill;
        row2.Controls.Add(_versionBox, 1, 0);
        root.Controls.Add(row2, 0, 1);

        // Files to extract
        var filesGroup = new GroupBox { Text = "Files to extract", Dock = DockStyle.Fill, AutoSize = true, Padding = new Padding(8) };
        var filesPanel = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3, AutoSize = true };
        _chkWowExe.Text = "Wow.exe";
        _chkWowExe.Checked = true;
        _chkWowExe.AutoSize = true;
        _chkLoader.Text = "Wow_loader.dll";
        _chkLoader.Checked = true;
        _chkLoader.AutoSize = true;
        filesPanel.Controls.Add(_chkWowExe, 0, 0);
        filesPanel.Controls.Add(_chkLoader, 0, 1);
        var extraRow = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, AutoSize = true };
        extraRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        extraRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        extraRow.Controls.Add(new Label { Text = "Other (comma-separated):", AutoSize = true, TextAlign = ContentAlignment.MiddleLeft, Anchor = AnchorStyles.Left }, 0, 0);
        _extraFiles.Dock = DockStyle.Fill;
        _extraFiles.PlaceholderText = "e.g. WowB.exe, World of Warcraft Launcher.exe";
        extraRow.Controls.Add(_extraFiles, 1, 0);
        filesPanel.Controls.Add(extraRow, 0, 2);
        filesGroup.Controls.Add(filesPanel);
        root.Controls.Add(filesGroup, 0, 2);

        // Output directory
        var row4 = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 1, AutoSize = true };
        row4.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 80));
        row4.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        row4.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        row4.Controls.Add(new Label { Text = "Output:", TextAlign = ContentAlignment.MiddleLeft, AutoSize = false, Dock = DockStyle.Fill }, 0, 0);
        _outputDir.Dock = DockStyle.Fill;
        _outputDir.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "WowVersionFix");
        row4.Controls.Add(_outputDir, 1, 0);
        _browseBtn.Text = "Browse…";
        _browseBtn.AutoSize = true;
        _browseBtn.Click += (_, _) =>
        {
            using var fbd = new FolderBrowserDialog { InitialDirectory = _outputDir.Text };
            if (fbd.ShowDialog(this) == DialogResult.OK) _outputDir.Text = fbd.SelectedPath;
        };
        row4.Controls.Add(_browseBtn, 2, 0);
        root.Controls.Add(row4, 0, 3);

        // Action buttons
        var row5 = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, FlowDirection = FlowDirection.LeftToRight };
        _extractBtn.Text = "Extract";
        _extractBtn.AutoSize = true;
        _extractBtn.Padding = new Padding(20, 4, 20, 4);
        _extractBtn.Click += async (_, _) => await RunExtractAsync();
        _openFolderBtn.Text = "Open Output Folder";
        _openFolderBtn.AutoSize = true;
        _openFolderBtn.Click += (_, _) =>
        {
            if (Directory.Exists(_outputDir.Text))
                Process.Start(new ProcessStartInfo("explorer.exe", $"\"{_outputDir.Text}\"") { UseShellExecute = true });
        };
        row5.Controls.Add(_extractBtn);
        row5.Controls.Add(_openFolderBtn);
        root.Controls.Add(row5, 0, 4);

        // Progress + status
        _progress.Dock = DockStyle.Fill;
        _progress.Style = ProgressBarStyle.Continuous;
        _progress.Height = 18;
        root.Controls.Add(_progress, 0, 5);
        _statusLabel.Dock = DockStyle.Fill;
        _statusLabel.AutoSize = false;
        _statusLabel.Height = 20;
        _statusLabel.Text = "Ready.";
        root.Controls.Add(_statusLabel, 0, 6);

        // Log box
        _log.Multiline = true;
        _log.ReadOnly = true;
        _log.ScrollBars = ScrollBars.Vertical;
        _log.Dock = DockStyle.Fill;
        _log.Font = new Font("Consolas", 9F);
        _log.BackColor = Color.Black;
        _log.ForeColor = Color.LightGray;
        root.Controls.Add(_log, 0, 7);

        Controls.Add(root);
    }

    private void SetStatus(string s)
    {
        if (InvokeRequired) { BeginInvoke(new Action<string>(SetStatus), s); return; }
        _statusLabel.Text = s;
    }

    private void AppendLog(string line)
    {
        if (InvokeRequired) { BeginInvoke(new Action<string>(AppendLog), line); return; }
        _log.AppendText(line + Environment.NewLine);
    }

    private async Task LoadBuildsAsync()
    {
        try
        {
            SetStatus("Loading builds from wago.tools…");
            _productBox.Enabled = false;
            _versionBox.Enabled = false;
            _extractBtn.Enabled = false;
            using var http = new HttpClient();
            http.DefaultRequestHeaders.UserAgent.ParseAdd("WowVersionFix/1.0");
            http.DefaultRequestHeaders.Accept.ParseAdd("application/json");
            http.Timeout = TimeSpan.FromSeconds(30);
            var json = await http.GetStringAsync("https://wago.tools/api/builds");
            var parsed = JsonSerializer.Deserialize<Dictionary<string, List<BuildEntry>>>(json, new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
            _builds = parsed ?? new();

            // Products sorted, "wow" first if present
            var products = _builds.Keys.OrderBy(k => k == "wow" ? "" : k).ToList();
            _productBox.Items.Clear();
            foreach (var p in products) _productBox.Items.Add(p);
            if (_productBox.Items.Count > 0) _productBox.SelectedIndex = 0;
            _productBox.Enabled = true;
            _versionBox.Enabled = true;
            _extractBtn.Enabled = true;
            SetStatus($"Loaded {products.Count} product(s).");
        }
        catch (Exception ex)
        {
            SetStatus("Failed to load builds.");
            MessageBox.Show(this, $"Could not load builds from wago.tools:\n\n{ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void RefreshVersionList()
    {
        _versionBox.Items.Clear();
        if (_productBox.SelectedItem is not string product) return;
        if (!_builds.TryGetValue(product, out var list)) return;
        foreach (var b in list.Where(b => !b.is_bgdl).OrderByDescending(b => b.created_at ?? ""))
        {
            _versionBox.Items.Add(new VersionItem(b));
        }
        if (_versionBox.Items.Count > 0) _versionBox.SelectedIndex = 0;
    }

    private async Task RunExtractAsync()
    {
        if (_versionBox.SelectedItem is not VersionItem v)
        {
            MessageBox.Show(this, "Pick a version first.", "WoW Version Fix", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        var files = new List<string>();
        if (_chkWowExe.Checked) files.Add("Wow.exe");
        if (_chkLoader.Checked) files.Add("Wow_loader.dll");
        foreach (var f in _extraFiles.Text.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            if (!string.IsNullOrWhiteSpace(f)) files.Add(f);

        if (files.Count == 0)
        {
            MessageBox.Show(this, "Tick at least one file to extract.", "WoW Version Fix", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        var outDir = Path.Combine(_outputDir.Text, $"{v.Build.product}_{v.Build.version}");
        try { Directory.CreateDirectory(outDir); }
        catch (Exception ex)
        {
            MessageBox.Show(this, $"Cannot create output folder:\n{ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        _extractBtn.Enabled = false;
        _progress.Style = ProgressBarStyle.Marquee;
        _log.Clear();
        SetStatus("Preparing TACTTool…");

        try
        {
            var tactPath = await EnsureTactToolAsync();
            var listFile = Path.Combine(Path.GetTempPath(), $"wowx_{Guid.NewGuid():N}.txt");
            await File.WriteAllLinesAsync(listFile, files);

            SetStatus($"Extracting {files.Count} file(s) from {v.Build.version}…");
            AppendLog($"> {v.Build.product} {v.Build.version}");
            AppendLog($"> build: {v.Build.build_config}");
            AppendLog($"> cdn:   {v.Build.cdn_config}");
            AppendLog($"> out:   {outDir}");
            AppendLog("");

            var psi = new ProcessStartInfo(tactPath)
            {
                ArgumentList = {
                    "-b", v.Build.build_config ?? "",
                    "-c", v.Build.cdn_config ?? "",
                    "-p", v.Build.product ?? "wow",
                    "-m", "list",
                    "-i", listFile,
                    "-o", outDir,
                },
                WorkingDirectory = Path.GetDirectoryName(tactPath),
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };

            _runCts = new CancellationTokenSource();
            using var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
            proc.OutputDataReceived += (_, e) => { if (e.Data != null) AppendLog(e.Data); };
            proc.ErrorDataReceived  += (_, e) => { if (e.Data != null) AppendLog("[err] " + e.Data); };
            proc.Start();
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
            await proc.WaitForExitAsync(_runCts.Token);

            try { File.Delete(listFile); } catch { }

            if (proc.ExitCode == 0)
            {
                SetStatus("Done.");
                AppendLog("");
                AppendLog("=== Extraction complete ===");
                var prompt = MessageBox.Show(this, $"Extraction complete.\n\nOpen {outDir}?", "WoW Version Fix", MessageBoxButtons.YesNo, MessageBoxIcon.Information);
                if (prompt == DialogResult.Yes)
                    Process.Start(new ProcessStartInfo("explorer.exe", $"\"{outDir}\"") { UseShellExecute = true });
            }
            else
            {
                SetStatus($"TACTTool exited with code {proc.ExitCode}.");
                MessageBox.Show(this, $"TACTTool exited with code {proc.ExitCode}. See log for details.", "Extraction failed", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }
        catch (Exception ex)
        {
            SetStatus("Error.");
            AppendLog("[error] " + ex.Message);
            MessageBox.Show(this, ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            _progress.Style = ProgressBarStyle.Continuous;
            _extractBtn.Enabled = true;
            _runCts?.Dispose();
            _runCts = null;
        }
    }

    private static async Task<string> EnsureTactToolAsync()
    {
        var dir = Path.Combine(Path.GetTempPath(), "WowVersionFix_TACT");
        Directory.CreateDirectory(dir);
        var target = Path.Combine(dir, "TACTTool.exe");
        if (!File.Exists(target) || new FileInfo(target).Length == 0)
        {
            var asm = Assembly.GetExecutingAssembly();
            var resName = asm.GetManifestResourceNames().FirstOrDefault(n => n.EndsWith("TACTTool.exe", StringComparison.OrdinalIgnoreCase))
                ?? throw new InvalidOperationException("Embedded TACTTool.exe resource not found.");
            using var src = asm.GetManifestResourceStream(resName)!;
            using var dst = File.Create(target);
            await src.CopyToAsync(dst);
        }
        return target;
    }

    private sealed class BuildEntry
    {
        public string? product { get; set; }
        public string? version { get; set; }
        public string? created_at { get; set; }
        public string? build_config { get; set; }
        public string? product_config { get; set; }
        public string? cdn_config { get; set; }
        public bool is_bgdl { get; set; }
    }

    private sealed class VersionItem
    {
        public BuildEntry Build { get; }
        public VersionItem(BuildEntry b) { Build = b; }
        public override string ToString() => $"{Build.version}    ({Build.created_at})";
    }
}
