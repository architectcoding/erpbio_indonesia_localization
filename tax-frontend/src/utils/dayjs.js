import dayjs from "dayjs"
import updateLocale from "dayjs/plugin/updateLocale"
import localizedFormat from "dayjs/plugin/localizedFormat"
import relativeTime from "dayjs/plugin/relativeTime"

dayjs.extend(updateLocale)
dayjs.extend(localizedFormat)
dayjs.extend(relativeTime)

export default dayjs
