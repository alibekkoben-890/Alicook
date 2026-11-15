package com.alicook.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;

/**
 * Receives the system alarm of the cooking timer. It fires even when the phone is asleep or the
 * app was closed. If the app is open the alarm rings inside it; otherwise a notification rings
 * with the alarm sound until the user opens or dismisses it.
 */
public class TimerReceiver extends BroadcastReceiver {
    static final int NOTIFICATION_ID = 7401;
    private static final String CHANNEL = "alicook_timer";

    @Override
    public void onReceive(Context context, Intent intent) {
        MainActivity a = MainActivity.current;
        if (a != null) {
            // The activity decides: ring in the app, or post the notification if it is in the background.
            if (a.hasPendingTimer()) a.timerFired();
            return;
        }
        String text = intent == null ? null : intent.getStringExtra("text");
        post(context.getApplicationContext(), text);
    }

    static void post(Context c, String text) {
        try {
            NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;
            if (text == null || text.isEmpty()) text = "\u23F1 Timer";
            Uri sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
            if (sound == null) sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
            AudioAttributes aa = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build();
            long[] pattern = {0, 600, 400, 600, 400, 600};
            Notification.Builder b;
            if (Build.VERSION.SDK_INT >= 26) {
                NotificationChannel ch = new NotificationChannel(CHANNEL, "Ali Cook timer",
                        NotificationManager.IMPORTANCE_HIGH);
                ch.setSound(sound, aa);
                ch.enableVibration(true);
                ch.setVibrationPattern(pattern);
                ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
                nm.createNotificationChannel(ch);
                b = new Notification.Builder(c, CHANNEL);
            } else {
                b = new Notification.Builder(c);
                b.setSound(sound, aa);
                b.setVibrate(pattern);
                b.setPriority(Notification.PRIORITY_MAX);
            }
            Intent open = new Intent(c, MainActivity.class);
            open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent pi = PendingIntent.getActivity(c, 2, open,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            b.setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
                    .setContentTitle("Ali Cook")
                    .setContentText(text)
                    .setContentIntent(pi)
                    .setAutoCancel(true)
                    .setCategory(Notification.CATEGORY_ALARM)
                    .setVisibility(Notification.VISIBILITY_PUBLIC)
                    .setShowWhen(true)
                    .setWhen(System.currentTimeMillis());
            Notification n = b.build();
            n.flags |= Notification.FLAG_INSISTENT;
            nm.notify(NOTIFICATION_ID, n);
        } catch (Exception ignored) {
        }
    }
}
