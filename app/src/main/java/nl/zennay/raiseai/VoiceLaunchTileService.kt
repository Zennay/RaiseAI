package nl.zennay.raiseai

import androidx.concurrent.futures.ResolvableFuture
import androidx.wear.protolayout.ActionBuilders
import androidx.wear.protolayout.ColorBuilders
import androidx.wear.protolayout.DimensionBuilders
import androidx.wear.protolayout.LayoutElementBuilders
import androidx.wear.protolayout.ModifiersBuilders
import androidx.wear.protolayout.TimelineBuilders
import androidx.wear.tiles.RequestBuilders
import androidx.wear.protolayout.ResourceBuilders
import androidx.wear.tiles.TileBuilders
import androidx.wear.tiles.TileService
import com.google.common.util.concurrent.ListenableFuture

/**
 * A no-sensor, no-network entry point for the two supported assistant experiences.
 *
 * Tile taps are explicit user actions. Neither background microphone capture nor
 * background activity launch privileges are needed; each tap opens an existing
 * in-app Activity and lets that Activity enforce its own permissions.
 */
class VoiceLaunchTileService : TileService() {
    override fun onTileRequest(
        requestParams: RequestBuilders.TileRequest
    ): ListenableFuture<TileBuilders.Tile> {
        val content = LayoutElementBuilders.Column.Builder()
            .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
            .addContent(label("RAISE AI", 19f, 0xFFFFFFFF.toInt()))
            .addContent(launchButton("Luisteren", NativeVoiceActivity::class.java.name, "voice"))
            .addContent(launchButton("Gemini", AssistantProxyActivity::class.java.name, "gemini"))
            .build()

        val root = LayoutElementBuilders.Box.Builder()
            .setWidth(DimensionBuilders.expand())
            .setHeight(DimensionBuilders.expand())
            .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
            .setVerticalAlignment(LayoutElementBuilders.VERTICAL_ALIGN_CENTER)
            .addContent(content)
            .build()

        val layout = LayoutElementBuilders.Layout.Builder().setRoot(root).build()
        val entry = TimelineBuilders.TimelineEntry.Builder().setLayout(layout).build()
        val tile = TileBuilders.Tile.Builder()
            .setResourcesVersion(RESOURCE_VERSION)
            .setTileTimeline(
                TimelineBuilders.Timeline.Builder().addTimelineEntry(entry).build()
            )
            .setFreshnessIntervalMillis(0L)
            .build()

        return completed(tile)
    }

    override fun onTileResourcesRequest(
        requestParams: RequestBuilders.ResourcesRequest
    ): ListenableFuture<ResourceBuilders.Resources> =
        completed(ResourceBuilders.Resources.Builder().setVersion(RESOURCE_VERSION).build())

    private fun launchButton(
        title: String,
        activityClass: String,
        id: String
    ): LayoutElementBuilders.Box {
        val action = ActionBuilders.LaunchAction.Builder()
            .setAndroidActivity(
                ActionBuilders.AndroidActivity.Builder()
                    .setPackageName(packageName)
                    .setClassName(activityClass)
                    .build()
            )
            .build()
        val clickable = ModifiersBuilders.Clickable.Builder()
            .setId("raise_$id")
            .setOnClick(action)
            .build()
        val background = ModifiersBuilders.Background.Builder()
            .setColor(ColorBuilders.argb(if (id == "voice") 0xFF3155CD.toInt() else 0xFF2B3048.toInt()))
            .build()
        return LayoutElementBuilders.Box.Builder()
            .setWidth(DimensionBuilders.dp(150f))
            .setHeight(DimensionBuilders.dp(54f))
            .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
            .setVerticalAlignment(LayoutElementBuilders.VERTICAL_ALIGN_CENTER)
            .setModifiers(
                ModifiersBuilders.Modifiers.Builder()
                    .setBackground(background)
                    .setClickable(clickable)
                    .build()
            )
            .addContent(label(title, 18f, 0xFFFFFFFF.toInt()))
            .build()
    }

    private fun label(
        text: String,
        size: Float,
        color: Int
    ): LayoutElementBuilders.Text = LayoutElementBuilders.Text.Builder()
        .setText(text)
        .setFontStyle(
            LayoutElementBuilders.FontStyle.Builder()
                .setSize(DimensionBuilders.sp(size))
                .setColor(ColorBuilders.argb(color))
                .build()
        )
        .build()

    private fun <T> completed(value: T): ListenableFuture<T> =
        ResolvableFuture.create<T>().apply { set(value) }

    companion object {
        private const val RESOURCE_VERSION = "voice-launch-1"
    }
}
