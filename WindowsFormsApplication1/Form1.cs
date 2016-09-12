using System;
using System.Data;
using System.Linq;
using System.Windows.Forms;
using System.IO;
using System.Net;
using ImageMagick;
using MetroFramework;
using System.Media;

namespace WindowsFormsApplication1
{
    public partial class Form1 : MetroFramework.Forms.MetroForm
    {
        private string test;

        public object RegexOptions { get; private set; }

        public Form1()
        {
            InitializeComponent();
        }

        private void Form1_Load(object sender, EventArgs e)
        {

        }

        private void button1_Click(object sender, EventArgs e)
        {
            FolderBrowserDialog fbd = new FolderBrowserDialog();

            DialogResult result = fbd.ShowDialog();

            if (!string.IsNullOrWhiteSpace(fbd.SelectedPath))
            {
                string[] files = Directory.GetFiles(fbd.SelectedPath, "*.png", SearchOption.AllDirectories);

                //System.Windows.Forms.MessageBox.Show("GFX files found: " + files.Length.ToString(), "Mod Files Found");

                {
                    //var files = Directory.GetFiles("C:\\path", "*.png", SearchOption.AllDirectories);

                    foreach (string filename in files)
                        using (MagickImage image = new MagickImage(filename))
                        {
                            image.Write(string.Format("{0}.pcx", filename));
                        }
                    foreach (string file in Directory.GetFiles(fbd.SelectedPath, "*.png", SearchOption.AllDirectories).Where(item => item.EndsWith(".png")))
                    {
                        File.Delete(file);

                    }
                    SoundPlayer simpleSound = new SoundPlayer(@"c:\Windows\Media\chimes.wav");
                    simpleSound.Play();
                    System.Windows.Forms.MessageBox.Show("Your mod has been converted");
                }
            }
        }




        private void linkLabel1_LinkClicked(object sender, LinkLabelLinkClickedEventArgs e)
        {
            try
            {
                System.Diagnostics.Process.Start("http://www.se7ensins.com/forums/threads/the-modding-of-isaac-vita-edition-the-binding-of-isaac-rebirth-mods-on-playstation-vita.1557403/");
            }
            catch { }

        }


        private void metroButton2_Click(object sender, EventArgs e)
        {
            FolderBrowserDialog fbd = new FolderBrowserDialog();

            DialogResult result = fbd.ShowDialog();

            if (!string.IsNullOrWhiteSpace(fbd.SelectedPath))
            {
                string[] files = Directory.GetFiles(fbd.SelectedPath, "*.png", SearchOption.AllDirectories);

                System.Windows.Forms.MessageBox.Show("Number of mods being converted:" + files.Length.ToString(), "Mod Files Found");
                metroLabel1.Text = "Converting Mods... This may take several minutes" + test;
                Refresh();

                {
                    //var files = Directory.GetFiles("C:\\path", "*.png", SearchOption.AllDirectories);

                    foreach (string filename in files)
                        using (MagickImage image = new MagickImage(filename))
                        {
                            image.Write(string.Format("{0}.pcx", filename.Replace(Path.GetExtension(filename), "")));
                        }
                    foreach (string file in Directory.GetFiles(fbd.SelectedPath, "*.png", SearchOption.AllDirectories).Where(item => item.EndsWith(".png")))
                    {
                        File.Delete(file);

                    }
                    foreach (string file in Directory.GetFiles(fbd.SelectedPath, "*.b", SearchOption.AllDirectories).Where(item => item.EndsWith(".b")))
                    {
                        File.Delete(file);

                    }
                    {

                    }

                    SoundPlayer simpleSound = new SoundPlayer(@"c:\Windows\Media\chimes.wav");
                    simpleSound.Play();
                    System.Windows.Forms.MessageBox.Show("Your mod has been converted");
                }
            }
        }

        private void metroButton3_Click(object sender, EventArgs e)
        {
            FolderBrowserDialog fbd = new FolderBrowserDialog();

            DialogResult result = fbd.ShowDialog();

            if (!string.IsNullOrWhiteSpace(fbd.SelectedPath))
            {
                string[] files = Directory.GetFiles(fbd.SelectedPath, "*.pcx", SearchOption.AllDirectories);

                System.Windows.Forms.MessageBox.Show("This may take a few moments..Amount of mod files being converted:" + files.Length.ToString(), "Mod Files Found");
                Cursor.Current = Cursors.WaitCursor;


                //System.Windows.Forms.MessageBox.Show("GFX files found: " + files.Length.ToString(), "Mod Files Found");

                {
                    //var files = Directory.GetFiles("C:\\path", "*.png", SearchOption.AllDirectories);

                    foreach (string filename in files)
                        using (MagickImage image = new MagickImage(filename))
                        {
                            image.Write(string.Format("{0}.png", filename));
                        }
                    foreach (string file in Directory.GetFiles(fbd.SelectedPath, "*.pcx", SearchOption.AllDirectories).Where(item => item.EndsWith(".pcx")))
                    {
                        File.Delete(file);

                    }
                    foreach (string file in Directory.GetFiles(fbd.SelectedPath, "*.b", SearchOption.AllDirectories).Where(item => item.EndsWith(".b")))
                    {
                        File.Delete(file);

                    }

                    SoundPlayer simpleSound = new SoundPlayer(@"c:\Windows\Media\chimes.wav");
                    simpleSound.Play();
                    System.Windows.Forms.MessageBox.Show("Your mod has been converted");
                    metroLabel1.Text = "AFTERBIRTH MODS ARE NOT SUPPORTED!" + test;
                    Refresh();
                }
            }
        }


        private void metroLink1_Click(object sender, EventArgs e)
        {
            try
            {
                System.Diagnostics.Process.Start("http://www.se7ensins.com/forums/threads/the-modding-of-isaac-vita-edition-the-binding-of-isaac-rebirth-mods-on-playstation-vita.1557403/");
            }
            catch { }
        }








        private void backgroundWorker_DoWork(object sender, System.ComponentModel.DoWorkEventArgs e)
        {

        }

        private void backgroundWorker_ProgressChanged(object sender, System.ComponentModel.ProgressChangedEventArgs e)
        {
            //lblStatus.Text = $"Uploaded {e.ProgressPercentage} %";
        }

        private void backgroundWorker_RunWorkerCompleted(object sender, System.ComponentModel.RunWorkerCompletedEventArgs e)
        {
            // lblStatus.Text = "Upload Complete!";
        }

        private void metroButton1_Click(object sender, EventArgs e)
        {
            FolderBrowserDialog fbd = new FolderBrowserDialog();

            DialogResult result = fbd.ShowDialog();

            if (!string.IsNullOrWhiteSpace(fbd.SelectedPath))
            {
                string[] files = Directory.GetFiles(fbd.SelectedPath, "*.pcx", SearchOption.AllDirectories);

                System.Windows.Forms.MessageBox.Show("Number of mods being converted:" + files.Length.ToString(), "Mod Files Found");
                metroLabel1.Text = "Converting Mods... This may take several minutes" + test;
                Refresh();

                //System.Windows.Forms.MessageBox.Show("GFX files found: " + files.Length.ToString(), "Mod Files Found");

                {
                    //var files = Directory.GetFiles("C:\\path", "*.png", SearchOption.AllDirectories);

                    foreach (string filename in files)
                        using (MagickImage image = new MagickImage(filename))
                        {
                            image.Write(string.Format("{0}.png", filename.Replace(Path.GetExtension(filename), "")));
                        }
                    foreach (string file in Directory.GetFiles(fbd.SelectedPath, "*.pcx", SearchOption.AllDirectories).Where(item => item.EndsWith(".pcx")))
                    {
                        File.Delete(file);

                    }
                    foreach (string file in Directory.GetFiles(fbd.SelectedPath, "*.b", SearchOption.AllDirectories).Where(item => item.EndsWith(".b")))
                    {
                        File.Delete(file);
                        

                    }

                    SoundPlayer simpleSound = new SoundPlayer(@"c:\Windows\Media\chimes.wav");
                    simpleSound.Play();
                    System.Windows.Forms.MessageBox.Show("Your mod has been converted");
                    metroLabel1.Text = "AFTERBIRTH MODS ARE NOT SUPPORTED!" + test;
                    Refresh();
                }
            }
        }

        private void metroLink2_Click(object sender, EventArgs e)
        {
            try
            {
                System.Diagnostics.Process.Start("https://twitter.com/Red7s");
            }
            catch { }
        }

        private void fileSystemWatcher1_Changed(object sender, FileSystemEventArgs e)
        {

        }

        private void metroLabel1_Click(object sender, EventArgs e)
        {

        }
    }
}

